"""Renewable API-backed single-owner lease for Telegram polling."""

import asyncio
import logging
import os
import socket
import uuid

from .api_gateway import BotApiError, BotApiUnavailableError
from .api_runtime import get_bot_api_gateway
from .settings import settings


logger = logging.getLogger(__name__)


class BotRuntimeLease:
    def __init__(self, *, name: str = "mvn:telegram_bot") -> None:
        self.name = name
        self.owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        self.acquired = False
        self.reason = "lease not requested"
        self.lost_event = asyncio.Event()
        self._heartbeat_task: asyncio.Task | None = None
        self._lease_deadline: float | None = None

    def _record_lease_deadline(self) -> None:
        self._lease_deadline = (
            asyncio.get_running_loop().time() + settings.BOT_RUNTIME_LEASE_SECONDS
        )

    @staticmethod
    def _next_retry_delay(delay: float) -> float:
        return min(
            max(float(settings.BOT_RUNTIME_RETRY_SECONDS), delay * 2),
            min(60.0, float(settings.BOT_RUNTIME_LEASE_SECONDS)),
        )

    def _mark_lost(self, reason: str) -> None:
        logger.error(reason)
        self.acquired = False
        self.lost_event.set()

    async def try_acquire(self) -> bool:
        result = await get_bot_api_gateway().acquire_runtime_lease(
            name=self.name,
            owner_id=self.owner_id,
            ttl_seconds=settings.BOT_RUNTIME_LEASE_SECONDS,
        )
        self.acquired = result.acquired
        self.reason = "runtime lease acquired" if result.acquired else "another bot owns runtime lease"
        if self.acquired and self._heartbeat_task is None:
            self._record_lease_deadline()
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return self.acquired

    async def wait_until_acquired(self) -> None:
        retry_delay = float(settings.BOT_RUNTIME_RETRY_SECONDS)
        while True:
            try:
                if await self.try_acquire():
                    return
            except BotApiUnavailableError as exc:
                logger.warning(
                    "Telegram polling lease API is unavailable; retrying in %.1fs: %s",
                    retry_delay,
                    exc,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = self._next_retry_delay(retry_delay)
                continue
            logger.info("Telegram polling lease is busy; retrying")
            retry_delay = float(settings.BOT_RUNTIME_RETRY_SECONDS)
            await asyncio.sleep(retry_delay)

    async def _heartbeat(self) -> None:
        while self.acquired:
            await asyncio.sleep(settings.BOT_RUNTIME_RENEW_SECONDS)
            retry_delay = float(settings.BOT_RUNTIME_RETRY_SECONDS)
            while self.acquired:
                try:
                    result = await get_bot_api_gateway().renew_runtime_lease(
                        name=self.name,
                        owner_id=self.owner_id,
                        ttl_seconds=settings.BOT_RUNTIME_LEASE_SECONDS,
                    )
                except BotApiUnavailableError as exc:
                    loop_time = asyncio.get_running_loop().time()
                    deadline = self._lease_deadline or loop_time
                    safety_margin = min(
                        5.0,
                        max(1.0, float(settings.BOT_RUNTIME_RENEW_SECONDS)),
                    )
                    remaining = deadline - loop_time - safety_margin
                    if remaining <= 0:
                        self._mark_lost(
                            "Telegram polling lease renewal deadline expired"
                        )
                        return
                    delay = min(retry_delay, remaining)
                    logger.warning(
                        "Telegram polling lease renewal is unavailable; "
                        "retrying in %.1fs: %s",
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    retry_delay = self._next_retry_delay(retry_delay)
                    continue
                except BotApiError as exc:
                    self._mark_lost(
                        f"Telegram polling lease renewal failed: {exc}"
                    )
                    return
                if not result.acquired:
                    self._mark_lost("Telegram polling lease ownership was lost")
                    return
                self._record_lease_deadline()
                break

    async def release(self) -> None:
        self.acquired = False
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            await get_bot_api_gateway().release_runtime_lease(
                name=self.name,
                owner_id=self.owner_id,
                ttl_seconds=settings.BOT_RUNTIME_LEASE_SECONDS,
            )
        except BotApiError:
            logger.warning("Telegram polling lease release failed", exc_info=True)
