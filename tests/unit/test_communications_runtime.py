import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import Settings
from models import CommunicationRuntimeState
from services.communications.delivery_worker import DeliveryRunOutcome
from services.communications.runtime import (
    CommunicationRuntimeConfig,
    CommunicationRuntimeLockUnavailable,
    CommunicationRuntimePipeline,
    CommunicationRuntimePrimaryRequired,
    CommunicationRuntimeShutdownTimeout,
    CommunicationRuntimeSupervisor,
    assert_primary_writable,
    run_communications_runtime,
)
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.runtime_lock_service import RuntimeLock


@pytest_asyncio.fixture
async def runtime_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(CommunicationRuntimeState.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def runtime_config(**overrides):
    config = CommunicationRuntimeConfig(
        enabled=True,
        app_role="primary",
        instance_id="test-runtime",
        poll_seconds=0.01,
        heartbeat_seconds=0.01,
        lock_retry_seconds=0.01,
        lock_check_seconds=0.01,
        db_probe_timeout_seconds=0.1,
        fencing_seconds=0,
        shutdown_seconds=0.2,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=15,
    )
    return replace(config, **overrides)


def test_communications_master_gate_defaults_to_off():
    assert Settings.model_fields["COMMUNICATIONS_WORKER_ENABLED"].default is False


async def own_mode(session_factory, mode: CommunicationRuntimeMode) -> None:
    async with session_factory() as session:
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=mode,
        )
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="test-runtime",
        )
        await session.commit()


class FakeProvider:
    channel = "telegram"

    def __init__(self, events):
        self.events = events

    async def close(self):
        self.events.append("provider-close")

    async def send(self, **_kwargs):  # pragma: no cover - worker is replaced
        raise AssertionError("fake provider send must not be called")


class FakeWorker:
    def __init__(self, events, outcome="idle"):
        self.events = events
        self.outcome = outcome

    async def run_once(self):
        self.events.append("delivery")
        return DeliveryRunOutcome(outcome=self.outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_status", "error_code"),
    [
        (CommunicationRuntimeMode.OFF, "disabled", None),
        (
            CommunicationRuntimeMode.CANARY,
            "paused",
            "canary_scope_unconfigured",
        ),
    ],
)
async def test_off_and_canary_modes_never_construct_provider(
    runtime_session_factory,
    mode,
    expected_status,
    error_code,
):
    await own_mode(runtime_session_factory, mode)

    def provider_factory():
        raise AssertionError("provider must remain dormant")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
    )
    assert await pipeline.run_cycle() is False
    await pipeline.close()

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state.status == expected_status
        assert state.last_error_code == error_code


@pytest.mark.asyncio
async def test_all_mode_runs_dispatch_then_one_delivery_and_closes_provider(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)
    events = []

    async def dispatch(_session, *, dispatcher_id):
        assert dispatcher_id == "test-runtime"
        events.append("dispatch")
        return SimpleNamespace(outcome="materialized")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=lambda: FakeProvider(events),
        worker_factory=lambda _provider: FakeWorker(events, outcome="sent"),
        dispatch=dispatch,
    )
    assert await pipeline.run_cycle() is True
    await pipeline.close()
    assert events == ["dispatch", "delivery", "provider-close"]

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state.status == "running"
        assert state.last_activity_at is not None


@pytest.mark.asyncio
async def test_immutable_gate_and_standby_role_do_not_touch_database_or_provider():
    touched = False

    def forbidden_factory():
        nonlocal touched
        touched = True
        raise AssertionError("disabled runtime must not create a session")

    for config in (
        runtime_config(enabled=False),
        runtime_config(app_role="standby"),
    ):
        await run_communications_runtime(
            config=config,
            session_factory=forbidden_factory,
            provider_factory=forbidden_factory,
            wait_when_disabled=False,
        )
    assert touched is False


class AcquiredLockService:
    lock = None

    @classmethod
    async def try_acquire(cls, *_args, **_kwargs):
        return cls.lock


@pytest.mark.asyncio
async def test_required_lock_failure_is_fail_closed(runtime_session_factory):
    class UnavailableLockService:
        @staticmethod
        async def try_acquire(*_args, **_kwargs):
            return RuntimeLock(
                "mvn:test",
                None,
                False,
                "required lock disabled",
                retryable=False,
            )

    pipeline_called = False

    def pipeline_factory():
        nonlocal pipeline_called
        pipeline_called = True
        raise AssertionError

    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=pipeline_factory,
        lock_service=UnavailableLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
    )
    with pytest.raises(CommunicationRuntimeLockUnavailable):
        await supervisor.run(asyncio.Event())
    assert pipeline_called is False


@pytest.mark.asyncio
async def test_provider_shutdown_finishes_before_advisory_lock_release(
    runtime_session_factory,
):
    events = []
    started = asyncio.Event()

    class OrderedLock(RuntimeLock):
        async def release(self):
            events.append("lock-release")
            await super().release()

    AcquiredLockService.lock = OrderedLock("mvn:test", None, True, "acquired")

    class Pipeline:
        async def run(self, stop_event):
            events.append("pipeline-start")
            started.set()
            await stop_event.wait()
            events.append("provider-close")

    stop_event = asyncio.Event()
    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=Pipeline,
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
    )
    task = asyncio.create_task(supervisor.run(stop_event))
    await asyncio.wait_for(started.wait(), timeout=1)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1)

    assert events == ["pipeline-start", "provider-close", "lock-release"]
    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state.status == CommunicationRuntimeStatus.STOPPED.value


@pytest.mark.asyncio
async def test_task_cancellation_uses_same_graceful_shutdown_order(
    runtime_session_factory,
):
    events = []
    started = asyncio.Event()

    class OrderedLock(RuntimeLock):
        async def release(self):
            events.append("lock-release")
            await super().release()

    AcquiredLockService.lock = OrderedLock("mvn:test", None, True, "acquired")

    class Pipeline:
        async def run(self, stop_event):
            started.set()
            try:
                await stop_event.wait()
            finally:
                events.append("provider-close")

    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=Pipeline,
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
    )
    task = asyncio.create_task(supervisor.run(asyncio.Event()))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["provider-close", "lock-release"]


@pytest.mark.asyncio
async def test_shutdown_timeout_calls_hard_stop_without_unlocking(
    runtime_session_factory,
):
    events = []
    started = asyncio.Event()
    unblock = asyncio.Event()

    class OrderedLock(RuntimeLock):
        async def release(self):
            events.append("lock-release")
            await super().release()

    AcquiredLockService.lock = OrderedLock("mvn:test", None, True, "acquired")

    class StuckPipeline:
        async def run(self, _stop_event):
            started.set()
            await unblock.wait()

    def hard_stop():
        events.append("hard-stop")
        unblock.set()

    stop_event = asyncio.Event()
    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(shutdown_seconds=0.01),
        session_factory=runtime_session_factory,
        pipeline_factory=StuckPipeline,
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        hard_stop=hard_stop,
    )
    task = asyncio.create_task(supervisor.run(stop_event))
    await asyncio.wait_for(started.wait(), timeout=1)
    stop_event.set()
    with pytest.raises(CommunicationRuntimeShutdownTimeout):
        await asyncio.wait_for(task, timeout=1)
    await asyncio.sleep(0)
    assert events == ["hard-stop"]


@pytest.mark.asyncio
async def test_primary_probe_fails_before_pipeline_and_releases_lock(
    runtime_session_factory,
):
    events = []

    class OrderedLock(RuntimeLock):
        async def release(self):
            events.append("lock-release")
            await super().release()

    AcquiredLockService.lock = OrderedLock("mvn:test", None, True, "acquired")

    async def reject(_factory):
        raise CommunicationRuntimePrimaryRequired("read-only")

    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=lambda: (_ for _ in ()).throw(AssertionError()),
        lock_service=AcquiredLockService,
        primary_probe=reject,
    )
    with pytest.raises(CommunicationRuntimePrimaryRequired):
        await supervisor.run(asyncio.Event())
    assert events == ["lock-release"]


@pytest.mark.asyncio
async def test_writable_probe_rejects_sqlite(runtime_session_factory):
    with pytest.raises(CommunicationRuntimePrimaryRequired, match="PostgreSQL"):
        await assert_primary_writable(runtime_session_factory)
