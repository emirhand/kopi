"""Async hardware mutex preventing concurrent USB/bus collisions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class HardwareBusyError(RuntimeError):
    """Raised when a non-blocking hardware lock acquisition encounters an active job."""

    def __init__(self, active_operation: str | None) -> None:
        self.active_operation = active_operation
        label = active_operation or "another operation"
        super().__init__(f"Hardware is currently busy with {label}")


class HardwareLock:
    """Async lock tracking active scanner/printer hardware operations."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._current_operation: str | None = None

    @property
    def is_busy(self) -> bool:
        return self._lock.locked()

    @property
    def current_operation(self) -> str | None:
        return self._current_operation

    @asynccontextmanager
    async def acquire(self, operation: str, *, wait: bool = False) -> AsyncIterator[None]:
        """Acquire exclusive hardware access for ``operation``."""
        if not wait and self._lock.locked():
            raise HardwareBusyError(self._current_operation)

        await self._lock.acquire()
        self._current_operation = operation
        try:
            yield
        finally:
            self._current_operation = None
            self._lock.release()
