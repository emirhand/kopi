"""Brute-force protection (attempt limits and exponential lockout) for PIN/password endpoints."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException

log = logging.getLogger("kopi.auth.rate_limit")
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

    def _buckets_for(self, scope: str, client_ip: str | None) -> list[tuple[str, int]]:
        max_attempts = self._max_attempts()
        if client_ip and client_ip.strip():
            return [
                (f"{scope}:ip:{client_ip.strip()}", max_attempts),
                (f"{scope}:global", max_attempts * 4),
            ]
        return [(scope, max_attempts)]

    def check(self, scope: str, client_ip: str | None = None) -> None:
        """Raise HTTP 429 if `scope` (for `client_ip` or global) is in a lockout delay window."""
        now = self.clock()
        buckets = self._buckets_for(scope, client_ip)
        max_remaining = 0
        with self._lock:
            for key, _limit in buckets:
                state = self._buckets.get(key)
                if state is not None and state.locked_until > now:
                    max_remaining = max(max_remaining, math.ceil(state.locked_until - now))
        if max_remaining > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Please wait {max_remaining}s before trying again.",
                headers={"Retry-After": str(max_remaining)},
            )

    def record_failure(self, scope: str, client_ip: str | None = None) -> None:
        """Record a failed attempt and apply lockout delay if threshold reached."""
        now = self.clock()
        base_lockout = self._base_lockout_sec()
        max_lockout = self._max_lockout_sec()
        buckets = self._buckets_for(scope, client_ip)

        with self._lock:
            for key, limit in buckets:
                state = self._buckets.setdefault(key, _BucketState())
                state.failures += 1
                if state.failures >= limit and base_lockout > 0:
                    over = state.failures - limit
                    delay = min(max_lockout, base_lockout * (2**over))
                    state.locked_until = now + delay
                    log.warning(
                        "auth_rate_limit_locked scope=%s key=%s failures=%d lockout_sec=%.0f",
                        scope,
                        key,
                        state.failures,
                        delay,
                    )
                else:
                    log.warning(
                        "auth_failure scope=%s key=%s failures=%d",
                        scope,
                        key,
                        state.failures,
                    )

    def record_success(self, scope: str, client_ip: str | None = None) -> None:
        """Reset failure count and lockout after a valid authentication."""
        buckets = self._buckets_for(scope, client_ip)
        with self._lock:
            for key, _limit in buckets:
                self._buckets.pop(key, None)

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
