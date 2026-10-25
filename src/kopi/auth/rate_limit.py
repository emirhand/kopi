"""Brute-force protection (attempt limits and exponential lockout) for PIN/password endpoints."""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_SECONDS = 30.0
DEFAULT_MAX_LOCKOUT_SECONDS = 300.0


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


@dataclass
class _BucketState:
    failures: int = 0
    locked_until: float = 0.0


@dataclass
class AuthRateLimiter:
    """In-memory attempt limiter with exponential lockout after threshold failures."""

    clock: Callable[[], float] = time.monotonic
    _buckets: dict[str, _BucketState] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _max_attempts(self) -> int:
        return _read_int_env("KOPI_AUTH_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)

    def _base_lockout_sec(self) -> float:
        return _read_float_env("KOPI_AUTH_LOCKOUT_SECONDS", DEFAULT_LOCKOUT_SECONDS)

    def _max_lockout_sec(self) -> float:
        return _read_float_env("KOPI_AUTH_MAX_LOCKOUT_SECONDS", DEFAULT_MAX_LOCKOUT_SECONDS)

    def check(self, scope: str) -> None:
        """Raise HTTP 429 if `scope` is currently in a lockout delay window."""
        now = self.clock()
        with self._lock:
            state = self._buckets.get(scope)
            if state is None or state.locked_until <= now:
                return
            remaining = max(1, math.ceil(state.locked_until - now))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Please wait {remaining}s before trying again.",
            headers={"Retry-After": str(remaining)},
        )

    def record_failure(self, scope: str) -> None:
        """Record a failed attempt for `scope` and apply lockout delay if threshold reached."""
        now = self.clock()
        max_attempts = self._max_attempts()
        base_lockout = self._base_lockout_sec()
        max_lockout = self._max_lockout_sec()

        with self._lock:
            state = self._buckets.setdefault(scope, _BucketState())
            state.failures += 1
            if state.failures >= max_attempts and base_lockout > 0:
                over = state.failures - max_attempts
                delay = min(max_lockout, base_lockout * (2**over))
                state.locked_until = now + delay

    def record_success(self, scope: str) -> None:
        """Reset failure count and lockout for `scope` after a valid authentication."""
        with self._lock:
            self._buckets.pop(scope, None)

    def reset(self) -> None:
        """Clear all rate-limit state (used in tests)."""
        with self._lock:
            self._buckets.clear()


_rate_limiter = AuthRateLimiter()


def get_auth_rate_limiter() -> AuthRateLimiter:
    """Return the process-wide AuthRateLimiter singleton."""
    return _rate_limiter


def reset_auth_rate_limiter() -> None:
    """Reset the process-wide AuthRateLimiter state."""
    _rate_limiter.reset()
