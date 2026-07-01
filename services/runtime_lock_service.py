import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logger import logger


@dataclass
class RuntimeLock:
    name: str
    session: Optional[AsyncSession]
    acquired: bool
    reason: str

    async def release(self) -> None:
        if not self.acquired or self.session is None:
            return
        try:
            bind = self.session.get_bind()
            dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
            if dialect_name == "postgresql":
                await self.session.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:lock_name))"),
                    {"lock_name": self.name},
                )
        finally:
            await self.session.close()
            self.acquired = False


class RuntimeLockService:
    @staticmethod
    async def try_acquire(
        session_factory: Callable[[], AsyncSession],
        lock_name: str,
    ) -> RuntimeLock:
        if not settings.RUNTIME_DB_LOCKS_ENABLED:
            return RuntimeLock(lock_name, None, True, "RUNTIME_DB_LOCKS_ENABLED=false")

        session = session_factory()
        bind = session.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect_name != "postgresql":
            return RuntimeLock(
                lock_name,
                session,
                True,
                f"database dialect {dialect_name!r} has no runtime lock",
            )

        try:
            result = await session.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:lock_name))"),
                {"lock_name": lock_name},
            )
            acquired = bool(result.scalar())
        except Exception:
            await session.close()
            raise

        if not acquired:
            await session.close()
            return RuntimeLock(lock_name, None, False, f"runtime lock {lock_name!r} is already held")

        return RuntimeLock(lock_name, session, True, f"runtime lock {lock_name!r} acquired")

    @staticmethod
    async def wait_until_acquired(
        session_factory: Callable[[], AsyncSession],
        lock_name: str,
    ) -> RuntimeLock:
        retry_seconds = max(1, int(settings.RUNTIME_LOCK_RETRY_SECONDS or 15))
        while True:
            lock = await RuntimeLockService.try_acquire(session_factory, lock_name)
            if lock.acquired:
                return lock
            logger.warning("%s; retrying in %ss", lock.reason, retry_seconds)
            await asyncio.sleep(retry_seconds)
