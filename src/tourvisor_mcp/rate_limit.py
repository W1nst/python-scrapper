"""A tiny async rate limiter used to protect the Tourvisor endpoints.

The MCP agent may retry a failing tool many times in the same turn.  Without a
brake this hammers Tourvisor, which then keeps answering with 401, which makes
the agent retry even more.  This module caps how often the *search* endpoint may
be hit and lets callers return a clear "stop retrying" message instead.
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Allow at most ``max_calls`` within any ``period`` seconds window."""

    def __init__(self, max_calls: int, period: float) -> None:
        self._max_calls = max_calls
        self._period = period
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Reserve a slot.

        Returns ``0.0`` when the call may proceed, otherwise the number of
        seconds the caller should wait before its next attempt.
        """
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < self._period]
            if len(self._calls) >= self._max_calls:
                oldest = self._calls[0]
                return max(0.0, self._period - (now - oldest))
            self._calls.append(now)
            return 0.0
