"""Process-local cost and concurrency guard for Manager content AI drafts."""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager


class ManagerContentAIRateLimitError(RuntimeError):
    def __init__(self, *, retry_after: int) -> None:
        self.retry_after = max(1, int(retry_after))
        super().__init__("Content AI request limit exceeded")


class ManagerContentAILimiter:
    def __init__(
        self,
        *,
        max_concurrent: int = 2,
        max_requests: int = 10,
        window_seconds: float = 60.0,
        acquire_timeout: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrent)))
        self._max_requests = max(1, int(max_requests))
        self._window_seconds = max(1.0, float(window_seconds))
        self._acquire_timeout = max(0.01, float(acquire_timeout))
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._events_lock = asyncio.Lock()
        self._cleanup_tick = 0

    @asynccontextmanager
    async def limit(self, key: str) -> AsyncIterator[None]:
        await self._consume_rate_slot(str(key or "unknown"))
        acquired = False
        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self._acquire_timeout,
                )
                acquired = True
            except TimeoutError as exc:
                raise ManagerContentAIRateLimitError(retry_after=1) from exc
            yield
        finally:
            if acquired:
                self._semaphore.release()

    async def _consume_rate_slot(self, key: str) -> None:
        now = self._clock()
        cutoff = now - self._window_seconds
        async with self._events_lock:
            self._cleanup_tick += 1
            if self._cleanup_tick % 128 == 0:
                stale_keys = [
                    identity
                    for identity, identity_events in self._events.items()
                    if not identity_events or identity_events[-1] <= cutoff
                ]
                for identity in stale_keys:
                    self._events.pop(identity, None)
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self._max_requests:
                retry_after = math.ceil(self._window_seconds - (now - events[0]))
                raise ManagerContentAIRateLimitError(retry_after=retry_after)
            events.append(now)


manager_content_ai_limiter = ManagerContentAILimiter()
