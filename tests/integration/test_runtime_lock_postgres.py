import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

import core.app_lifespan as scheduler_runtime
from services.runtime_lock_service import RuntimeLockService


@pytest.mark.asyncio
async def test_postgres_runtime_lock_survives_without_transaction_and_recovers_backend_loss(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    lock_name = f"mvn:test:runtime-lock:{uuid4()}"
    owner_lock = contender_lock = replacement_lock = None
    checkout_count = 0

    def count_checkout(_dbapi_connection, _connection_record, _connection_proxy):
        nonlocal checkout_count
        checkout_count += 1

    event.listen(db_engine.sync_engine, "checkout", count_checkout)
    try:
        owner_lock = await RuntimeLockService.try_acquire(
            session_factory,
            lock_name,
            required=True,
        )
        assert owner_lock.acquired is True
        assert owner_lock.connection is not None
        assert await owner_lock.is_held() is True

        owner_pid = int(
            (
                await owner_lock.connection.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
        )
        async with db_engine.connect() as observer:
            observer = await observer.execution_options(isolation_level="AUTOCOMMIT")
            activity = (
                await observer.execute(
                    text(
                        """
                        SELECT state, xact_start
                        FROM pg_stat_activity
                        WHERE pid = :pid
                        """
                    ),
                    {"pid": owner_pid},
                )
            ).mappings().one()
            assert activity["state"] != "idle in transaction"
            assert activity["xact_start"] is None

            contender_lock = await RuntimeLockService.try_acquire(
                session_factory,
                lock_name,
                required=True,
            )
            assert contender_lock.acquired is False
            assert contender_lock.retryable is True

            terminated = (
                await observer.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": owner_pid},
                )
            ).scalar_one()
            assert terminated is True

            checkouts_before_liveness = checkout_count
            for _ in range(20):
                if not await owner_lock.is_held():
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("terminated runtime-lock backend still reports the lock as held")

            # A failed liveness probe must invalidate the original connection,
            # not reconnect it under the same RuntimeLock instance.
            assert checkout_count == checkouts_before_liveness
            assert owner_lock.acquired is False
            assert owner_lock.connection is None

            for _ in range(20):
                candidate = await RuntimeLockService.try_acquire(
                    session_factory,
                    lock_name,
                    required=True,
                )
                if candidate.acquired:
                    replacement_lock = candidate
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("runtime lock was not reacquired after backend termination")

            assert replacement_lock is not None
            assert await replacement_lock.is_held() is True
    finally:
        try:
            for runtime_lock in (replacement_lock, contender_lock, owner_lock):
                if runtime_lock is not None:
                    await runtime_lock.release()
        finally:
            event.remove(db_engine.sync_engine, "checkout", count_checkout)


@pytest.mark.asyncio
async def test_real_postgres_fencing_prevents_two_supervisor_loops_from_overlapping(
    db_engine,
    monkeypatch,
):
    assert db_engine.dialect.name == "postgresql"
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(scheduler_runtime, "async_session_maker", session_factory)
    monkeypatch.setattr(
        scheduler_runtime.settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        scheduler_runtime.settings,
        "RUNTIME_LOCK_RETRY_SECONDS",
        1,
        raising=False,
    )
    monkeypatch.setattr(
        scheduler_runtime,
        "_scheduler_lock_check_seconds",
        lambda: 0.05,
    )
    monkeypatch.setattr(
        scheduler_runtime,
        "_scheduler_lock_probe_timeout_seconds",
        lambda: 0.5,
    )
    monkeypatch.setattr(
        scheduler_runtime,
        "_scheduler_lock_fencing_grace_seconds",
        lambda: 0.6,
    )

    async def hold_failed_owner_before_retry():
        await asyncio.sleep(10)

    monkeypatch.setattr(
        scheduler_runtime,
        "_wait_before_scheduler_retry",
        hold_failed_owner_before_retry,
    )
    fail_stop_called = asyncio.Event()
    fail_stop_calls = 0

    def fail_stop():
        nonlocal fail_stop_calls
        fail_stop_calls += 1
        fail_stop_called.set()

    monkeypatch.setattr(
        scheduler_runtime,
        "_scheduler_runtime_fail_stop",
        fail_stop,
    )
    resume_jobs = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler_runtime, "_resume_catalog_import_jobs", resume_jobs)
    started = []
    cancelled = []
    active_loops = 0
    maximum_active_loops = 0

    def start(app):
        started_event = asyncio.Event()
        cancelled_event = asyncio.Event()
        started.append(started_event)
        cancelled.append(cancelled_event)

        async def loop():
            nonlocal active_loops, maximum_active_loops
            active_loops += 1
            maximum_active_loops = max(maximum_active_loops, active_loops)
            started_event.set()
            try:
                await asyncio.Event().wait()
            finally:
                active_loops -= 1
                cancelled_event.set()

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    monkeypatch.setattr(scheduler_runtime, "_start_scheduler_loop", start)
    first_app = SimpleNamespace(state=SimpleNamespace())
    second_app = SimpleNamespace(state=SimpleNamespace())
    first_supervisor = asyncio.create_task(
        scheduler_runtime._run_scheduler_supervisor(first_app)
    )
    second_supervisor = None

    try:
        await asyncio.wait_for(_wait_for_count(started, 1), timeout=2)
        await asyncio.wait_for(started[0].wait(), timeout=2)
        first_lock = first_app.state.scheduler_runtime_lock
        first_pid = int(
            (
                await first_lock.connection.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
        )
        async with db_engine.connect() as observer:
            observer = await observer.execution_options(isolation_level="AUTOCOMMIT")
            assert (
                await observer.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": first_pid},
                )
            ).scalar_one() is True

        second_supervisor = asyncio.create_task(
            scheduler_runtime._run_scheduler_supervisor(second_app)
        )
        await asyncio.wait_for(_wait_for_count(started, 2), timeout=5)
        await asyncio.wait_for(started[1].wait(), timeout=2)
        await asyncio.wait_for(fail_stop_called.wait(), timeout=1)

        assert cancelled[0].is_set()
        assert maximum_active_loops == 1
        assert fail_stop_calls == 1
        assert first_app.state.scheduler_runtime["status"] == "faulted"
        assert first_app.state.scheduler_runtime["reason"] == "ownership_lost"
        assert second_app.state.scheduler_runtime["status"] == "running"
        assert resume_jobs.await_count == 2
    finally:
        tasks = [first_supervisor]
        if second_supervisor is not None:
            tasks.append(second_supervisor)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert cancelled[1].is_set()
    assert maximum_active_loops == 1


async def _wait_for_count(items, expected):
    while len(items) < expected:
        await asyncio.sleep(0)
