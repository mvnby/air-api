import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from core.config import settings
from core.logger import logger


_LOCK_IS_HELD_QUERY = text(
    """
    WITH lock_key AS (
        SELECT hashtext(:lock_name)::bigint AS value
    )
    SELECT EXISTS (
        SELECT 1
        FROM pg_locks, lock_key
        WHERE locktype = 'advisory'
          AND pid = pg_backend_pid()
          AND granted
          AND classid = (((lock_key.value >> 32) & 4294967295)::oid)
          AND objid = ((lock_key.value & 4294967295)::oid)
          AND objsubid = 1
    )
    """
)


async def _invalidate_and_close(connection: AsyncConnection) -> None:
    """Discard a connection whose advisory-lock state is no longer trustworthy."""
    try:
        await connection.invalidate()
    except Exception:
        logger.exception("Failed to invalidate a runtime-lock database connection.")
    finally:
        with suppress(Exception):
            await connection.close()


@dataclass
class RuntimeLock:
    name: str
    connection: Optional[AsyncConnection]
    acquired: bool
    reason: str
    retryable: bool = False

    async def is_held(self) -> bool:
        """Check this lock on the same pinned PostgreSQL connection."""
        connection = self.connection
        if not self.acquired:
            return False
        if connection is None:
            # Compatibility mode (locks explicitly disabled or a non-PostgreSQL
            # local/test database) has no database-backed lock to probe.
            return True
        if connection.closed:
            self.acquired = False
            self.connection = None
            return False

        try:
            result = await connection.execute(
                _LOCK_IS_HELD_QUERY,
                {"lock_name": self.name},
            )
            held = bool(result.scalar())
        except asyncio.CancelledError:
            self.acquired = False
            self.connection = None
            await _invalidate_and_close(connection)
            raise
        except Exception:
            logger.exception("Runtime lock %r liveness check failed.", self.name)
            self.acquired = False
            self.connection = None
            await _invalidate_and_close(connection)
            return False

        if not held:
            self.acquired = False
            self.connection = None
            try:
                await connection.close()
            except asyncio.CancelledError:
                await _invalidate_and_close(connection)
                raise
            except Exception:
                await _invalidate_and_close(connection)
        return held

    async def release(self) -> None:
        if not self.acquired:
            return

        connection = self.connection
        self.acquired = False
        self.connection = None
        if connection is None:
            return

        try:
            result = await connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_name))"),
                {"lock_name": self.name},
            )
            if not bool(result.scalar()):
                logger.warning("Runtime lock %r was not held during release.", self.name)
        except BaseException:
            # Returning an uncertain session-level lock to the pool can strand it
            # on an unrelated future checkout. Invalidating physically drops it.
            await _invalidate_and_close(connection)
            raise
        else:
            try:
                await connection.close()
            except BaseException:
                await _invalidate_and_close(connection)
                raise


class RuntimeLockService:
    @staticmethod
    async def _resolve_engine(
        session_factory: Callable[[], AsyncSession],
    ) -> tuple[AsyncEngine, str]:
        session = session_factory()
        try:
            async_bind = session.bind
            sync_bind = session.get_bind()
            dialect_name = getattr(getattr(sync_bind, "dialect", None), "name", "")
        finally:
            await session.close()

        if isinstance(async_bind, AsyncConnection):
            return async_bind.engine, dialect_name
        if isinstance(async_bind, AsyncEngine):
            return async_bind, dialect_name
        raise RuntimeError("Runtime lock session factory has no async engine bind")

    @staticmethod
    async def try_acquire(
        session_factory: Callable[[], AsyncSession],
        lock_name: str,
        *,
        required: bool = False,
    ) -> RuntimeLock:
        if not settings.RUNTIME_DB_LOCKS_ENABLED:
            if required:
                return RuntimeLock(
                    lock_name,
                    None,
                    False,
                    "runtime database lock is required but RUNTIME_DB_LOCKS_ENABLED=false",
                )
            return RuntimeLock(lock_name, None, True, "RUNTIME_DB_LOCKS_ENABLED=false")

        engine, dialect_name = await RuntimeLockService._resolve_engine(session_factory)
        if dialect_name != "postgresql":
            if required:
                return RuntimeLock(
                    lock_name,
                    None,
                    False,
                    f"runtime database lock is required but dialect is {dialect_name!r}",
                )
            return RuntimeLock(
                lock_name,
                None,
                True,
                f"database dialect {dialect_name!r} has no runtime lock",
            )

        connection = await engine.connect()
        try:
            # Session-level advisory locks survive transaction boundaries. Keep a
            # dedicated connection in AUTOCOMMIT so it is never idle-in-transaction
            # and cannot be handed to another consumer until explicit unlock.
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:lock_name))"),
                {"lock_name": lock_name},
            )
            acquired = bool(result.scalar())
        except BaseException:
            await _invalidate_and_close(connection)
            raise

        if not acquired:
            await connection.close()
            return RuntimeLock(
                lock_name,
                None,
                False,
                f"runtime lock {lock_name!r} is already held",
                retryable=True,
            )

        return RuntimeLock(
            lock_name,
            connection,
            True,
            f"runtime lock {lock_name!r} acquired",
        )

    @staticmethod
    async def wait_until_acquired(
        session_factory: Callable[[], AsyncSession],
        lock_name: str,
        *,
        required: bool = False,
    ) -> RuntimeLock:
        retry_seconds = max(1, int(settings.RUNTIME_LOCK_RETRY_SECONDS or 15))
        while True:
            lock = await RuntimeLockService.try_acquire(
                session_factory,
                lock_name,
                required=required,
            )
            if lock.acquired or not lock.retryable:
                return lock
            logger.warning("%s; retrying in %ss", lock.reason, retry_seconds)
            await asyncio.sleep(retry_seconds)
