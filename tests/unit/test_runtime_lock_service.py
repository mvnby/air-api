import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from services import runtime_lock_service as runtime_locks
from services.runtime_lock_service import RuntimeLock, RuntimeLockService


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class FakeConnection:
    def __init__(self, *, acquire_result=True, liveness_result=True, unlock_result=True):
        self.acquire_result = acquire_result
        self.liveness_result = liveness_result
        self.unlock_result = unlock_result
        self.closed = False
        self.invalidated = False
        self.execution_options_calls = []
        self.execute_calls = []
        self.acquire_error = None
        self.liveness_error = None
        self.unlock_error = None

    async def execution_options(self, **options):
        self.execution_options_calls.append(options)
        return self

    async def execute(self, statement, parameters):
        sql = str(statement)
        self.execute_calls.append((sql, parameters))
        if "pg_try_advisory_lock" in sql:
            if self.acquire_error is not None:
                raise self.acquire_error
            return FakeResult(self.acquire_result)
        if "pg_advisory_unlock" in sql:
            if self.unlock_error is not None:
                raise self.unlock_error
            return FakeResult(self.unlock_result)
        if "pg_locks" in sql:
            if self.liveness_error is not None:
                raise self.liveness_error
            return FakeResult(self.liveness_result)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def invalidate(self):
        self.invalidated = True

    async def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection
        self.connect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        return self.connection


def _enable_runtime_locks(monkeypatch):
    monkeypatch.setattr(
        runtime_locks.settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        True,
        raising=False,
    )


@pytest.mark.asyncio
async def test_postgres_lock_uses_one_pinned_autocommit_connection(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    connection = FakeConnection()
    engine = FakeEngine(connection)
    resolve_engine = AsyncMock(return_value=(engine, "postgresql"))
    monkeypatch.setattr(RuntimeLockService, "_resolve_engine", resolve_engine)
    session_factory = Mock()

    lock = await RuntimeLockService.try_acquire(session_factory, "mvn:test")

    assert lock.acquired is True
    assert lock.connection is connection
    assert connection.closed is False
    assert connection.execution_options_calls == [{"isolation_level": "AUTOCOMMIT"}]
    assert await lock.is_held() is True

    await lock.release()

    assert lock.acquired is False
    assert lock.connection is None
    assert connection.closed is True
    assert connection.invalidated is False
    assert engine.connect_calls == 1
    assert [
        "pg_try_advisory_lock"
        if "pg_try_advisory_lock" in sql
        else "pg_advisory_unlock"
        if "pg_advisory_unlock" in sql
        else "pg_locks"
        for sql, _ in connection.execute_calls
    ] == ["pg_try_advisory_lock", "pg_locks", "pg_advisory_unlock"]


@pytest.mark.asyncio
async def test_held_postgres_lock_closes_connection_and_is_retryable(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    connection = FakeConnection(acquire_result=False)
    engine = FakeEngine(connection)
    monkeypatch.setattr(
        RuntimeLockService,
        "_resolve_engine",
        AsyncMock(return_value=(engine, "postgresql")),
    )

    lock = await RuntimeLockService.try_acquire(Mock(), "mvn:test")

    assert lock.acquired is False
    assert lock.retryable is True
    assert lock.connection is None
    assert connection.closed is True
    assert connection.invalidated is False


@pytest.mark.asyncio
async def test_required_lock_fails_closed_when_database_locks_disabled(monkeypatch):
    monkeypatch.setattr(
        runtime_locks.settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        False,
        raising=False,
    )
    session_factory = Mock()

    required_lock = await RuntimeLockService.try_acquire(
        session_factory,
        "mvn:test",
        required=True,
    )
    compatibility_lock = await RuntimeLockService.try_acquire(session_factory, "mvn:test")

    assert required_lock.acquired is False
    assert required_lock.retryable is False
    assert "required" in required_lock.reason
    assert compatibility_lock.acquired is True
    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_required_lock_fails_closed_for_non_postgres(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    engine = FakeEngine(FakeConnection())
    monkeypatch.setattr(
        RuntimeLockService,
        "_resolve_engine",
        AsyncMock(return_value=(engine, "sqlite")),
    )

    lock = await RuntimeLockService.wait_until_acquired(
        Mock(),
        "mvn:test",
        required=True,
    )

    assert lock.acquired is False
    assert lock.retryable is False
    assert "sqlite" in lock.reason
    assert engine.connect_calls == 0


@pytest.mark.asyncio
async def test_real_session_factory_resolves_non_postgres_fail_closed(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    engine = create_async_engine("sqlite+aiosqlite://")
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        lock = await RuntimeLockService.try_acquire(
            session_factory,
            "mvn:test",
            required=True,
        )
    finally:
        await engine.dispose()

    assert lock.acquired is False
    assert lock.connection is None
    assert "sqlite" in lock.reason


@pytest.mark.asyncio
async def test_lock_liveness_returns_false_for_closed_or_failed_connection():
    closed_connection = FakeConnection()
    closed_connection.closed = True
    closed_lock = RuntimeLock("mvn:closed", closed_connection, True, "test")

    assert await closed_lock.is_held() is False
    assert closed_connection.execute_calls == []

    failed_connection = FakeConnection()
    failed_connection.liveness_error = RuntimeError("connection lost")
    failed_lock = RuntimeLock("mvn:failed", failed_connection, True, "test")

    assert await failed_lock.is_held() is False
    failed_connection.liveness_error = None
    await failed_lock.release()


@pytest.mark.asyncio
async def test_lock_liveness_failure_does_not_reconnect(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    connection = FakeConnection()
    engine = FakeEngine(connection)
    monkeypatch.setattr(
        RuntimeLockService,
        "_resolve_engine",
        AsyncMock(return_value=(engine, "postgresql")),
    )
    lock = await RuntimeLockService.try_acquire(Mock(), "mvn:test")
    connection.liveness_error = ConnectionError("backend terminated")

    assert await lock.is_held() is False
    assert engine.connect_calls == 1

    connection.liveness_error = None
    await lock.release()


@pytest.mark.asyncio
async def test_release_failure_invalidates_connection_instead_of_pooling_it():
    connection = FakeConnection()
    connection.unlock_error = ConnectionError("backend lost during unlock")
    lock = RuntimeLock("mvn:test", connection, True, "test")

    with pytest.raises(ConnectionError, match="backend lost"):
        await lock.release()

    assert lock.acquired is False
    assert lock.connection is None
    assert connection.invalidated is True
    assert connection.closed is True


@pytest.mark.asyncio
async def test_cancelled_acquire_invalidates_uncertain_connection(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    connection = FakeConnection()
    connection.acquire_error = asyncio.CancelledError()
    engine = FakeEngine(connection)
    monkeypatch.setattr(
        RuntimeLockService,
        "_resolve_engine",
        AsyncMock(return_value=(engine, "postgresql")),
    )

    with pytest.raises(asyncio.CancelledError):
        await RuntimeLockService.try_acquire(Mock(), "mvn:test")

    assert connection.invalidated is True
    assert connection.closed is True


@pytest.mark.asyncio
async def test_wait_until_acquired_is_cancellable_during_backoff(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    held_lock = RuntimeLock(
        "mvn:test",
        None,
        False,
        "held elsewhere",
        retryable=True,
    )
    try_acquire = AsyncMock(return_value=held_lock)
    monkeypatch.setattr(RuntimeLockService, "try_acquire", try_acquire)
    sleeping = asyncio.Event()

    async def sleep_forever(_seconds):
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime_locks.asyncio, "sleep", sleep_forever)
    task = asyncio.create_task(
        RuntimeLockService.wait_until_acquired(Mock(), "mvn:test")
    )
    await asyncio.wait_for(sleeping.wait(), timeout=0.2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    try_acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_until_acquired_retries_held_lock_then_returns_new_owner(monkeypatch):
    _enable_runtime_locks(monkeypatch)
    held_lock = RuntimeLock(
        "mvn:test",
        None,
        False,
        "held elsewhere",
        retryable=True,
    )
    acquired_lock = RuntimeLock("mvn:test", None, True, "acquired")
    try_acquire = AsyncMock(side_effect=[held_lock, acquired_lock])
    monkeypatch.setattr(RuntimeLockService, "try_acquire", try_acquire)
    backoff_started = asyncio.Event()
    allow_retry = asyncio.Event()

    async def controlled_sleep(_seconds):
        backoff_started.set()
        await allow_retry.wait()

    monkeypatch.setattr(runtime_locks.asyncio, "sleep", controlled_sleep)
    task = asyncio.create_task(
        RuntimeLockService.wait_until_acquired(Mock(), "mvn:test")
    )
    await asyncio.wait_for(backoff_started.wait(), timeout=0.2)

    allow_retry.set()
    result = await asyncio.wait_for(task, timeout=0.2)

    assert result is acquired_lock
    assert try_acquire.await_count == 2
