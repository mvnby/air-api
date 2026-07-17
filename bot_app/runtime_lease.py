"""Renewable API-backed single-owner lease for Telegram polling."""

import asyncio
import logging
import os
import socket
import uuid

from .api_gateway import BotApiError
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

    async def try_acquire(self) -> bool:
        result = await get_bot_api_gateway().acquire_runtime_lease(
            name=self.name,
            owner_id=self.owner_id,
            ttl_seconds=settings.BOT_RUNTIME_LEASE_SECONDS,
        )
        self.acquired = result.acquired
        self.reason = "runtime lease acquired" if result.acquired else "another bot owns runtime lease"
        if self.acquired and self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return self.acquired

    async def wait_until_acquired(self) -> None:
        while not await self.try_acquire():
            logger.info("Telegram polling lease is busy; retrying")
            await asyncio.sleep(settings.BOT_RUNTIME_RETRY_SECONDS)

    async def _heartbeat(self) -> None:
        while self.acquired:
            await asyncio.sleep(settings.BOT_RUNTIME_RENEW_SECONDS)
            try:
                result = await get_bot_api_gateway().renew_runtime_lease(
                    name=self.name,
                    owner_id=self.owner_id,
                    ttl_seconds=settings.BOT_RUNTIME_LEASE_SECONDS,
                )
            except BotApiError:
                logger.exception("Telegram polling lease renewal failed")
                self.acquired = False
                self.lost_event.set()
                return
            if not result.acquired:
                logger.error("Telegram polling lease ownership was lost")
                self.acquired = False
                self.lost_event.set()
                return

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
