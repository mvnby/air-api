import asyncio
import io
import logging
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import Settings
from models import CommunicationRuntimeState
from services.communications.delivery_worker import DeliveryRunOutcome
from services.communications.processing_scope import CommunicationProcessingScope
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
from services.communications.runtime_config import CommunicationRuntimeStopRequested
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.runtime_lock_service import RuntimeLock


ASYNC_TEST_TIMEOUT_SECONDS = 5


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
        allow_all_mode=True,
        instance_id="test-runtime",
        poll_seconds=0.01,
        heartbeat_seconds=0.01,
        lock_retry_seconds=0.01,
        lock_check_seconds=0.01,
        db_probe_timeout_seconds=1,
        fencing_seconds=6,
        shutdown_seconds=0.2,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=30,
    )
    return replace(config, **overrides)


def test_communications_master_gate_defaults_to_off():
    assert Settings.model_fields["COMMUNICATIONS_WORKER_ENABLED"].default is False
    assert (
        Settings.model_fields["COMMUNICATIONS_WORKER_ALLOW_ALL_MODE"].default
        is False
    )
    default_config = CommunicationRuntimeConfig(enabled=False, app_role="primary")
    assert default_config.deployment_enabled is False
    assert default_config.allow_all_mode is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": "false"},
        {"allow_all_mode": "false"},
        {"allow_all_mode": 1},
    ],
)
def test_runtime_rejects_truthy_non_boolean_deployment_gates(overrides):
    with pytest.raises(ValueError, match="deployment gates must be boolean"):
        runtime_config(**overrides)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("poll_seconds", 0),
        ("heartbeat_seconds", math.inf),
        ("lock_retry_seconds", math.nan),
        ("lock_check_seconds", -1),
        ("db_probe_timeout_seconds", 0),
        ("fencing_seconds", 0),
        ("shutdown_seconds", math.inf),
        ("provider_timeout_seconds", math.nan),
        ("provider_close_seconds", 0),
    ],
)
def test_runtime_rejects_non_finite_and_non_positive_durations(
    field_name,
    invalid_value,
):
    with pytest.raises(ValueError, match="finite and greater than zero"):
        runtime_config(**{field_name: invalid_value})


def test_fencing_window_must_exceed_detection_and_shutdown_bound():
    base = runtime_config()
    handoff_window = (
        base.lock_check_seconds
        + (4 * base.db_probe_timeout_seconds)
        + base.shutdown_seconds
        + base.provider_timeout_seconds
        + base.provider_close_seconds
    )
    with pytest.raises(ValueError, match="strictly greater"):
        replace(base, fencing_seconds=handoff_window)
    assert replace(
        base,
        fencing_seconds=handoff_window + 0.01,
    ).fencing_seconds > handoff_window


@pytest.mark.parametrize("invalid_lease", [0, math.inf, math.nan, 15.5])
def test_runtime_rejects_invalid_or_non_finite_lease(invalid_lease):
    with pytest.raises(ValueError):
        runtime_config(lease_seconds=invalid_lease)


async def allow_safety(_scope: CommunicationProcessingScope) -> None:
    return None


async def instant_fencing(stop_event: asyncio.Event, _seconds: float) -> bool:
    return stop_event.is_set()


async def own_mode(
    session_factory,
    mode: CommunicationRuntimeMode,
    *,
    canary_run_id: str | None = None,
):
    async with session_factory() as session:
        control = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=mode,
            canary_run_id=canary_run_id,
        )
        owned = await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="test-runtime",
        )
        await session.commit()
        assert owned.control_revision == control.control_revision
        return owned


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
async def test_all_mode_runs_dispatch_then_one_delivery_and_closes_provider(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)
    events = []

    async def dispatch(_session, *, dispatcher_id, scope):
        assert dispatcher_id == "test-runtime"
        assert scope.mode == "all"
        events.append("dispatch")
        return SimpleNamespace(outcome="materialized")

    def worker_factory(_provider, scope):
        assert scope.mode == "all"
        return FakeWorker(events, outcome="sent")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=lambda: FakeProvider(events),
        safety_check=allow_safety,
        worker_factory=worker_factory,
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
async def test_stop_set_after_dispatch_prevents_delivery_and_provider_creation(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)
    stop_event = asyncio.Event()
    events = []

    async def safety_check(_scope):
        if stop_event.is_set():
            raise CommunicationRuntimeStopRequested("stop requested")

    async def dispatch(_session, *, dispatcher_id, scope):
        assert dispatcher_id == "test-runtime"
        assert scope.mode == "all"
        events.append("dispatch")
        stop_event.set()
        return SimpleNamespace(outcome="materialized")

    def provider_factory():
        events.append("provider-created")
        return FakeProvider(events)

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=safety_check,
        worker_factory=lambda _provider, _scope: FakeWorker(
            events,
            outcome="sent",
        ),
        dispatch=dispatch,
    )
    await pipeline.run(stop_event)

    assert events == ["dispatch"]


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

    def pipeline_factory(_safety_check):
        nonlocal pipeline_called
        pipeline_called = True
        raise AssertionError

    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=pipeline_factory,
        lock_service=UnavailableLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        fencing_wait=instant_fencing,
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
        pipeline_factory=lambda _safety_check: Pipeline(),
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        fencing_wait=instant_fencing,
    )
    task = asyncio.create_task(supervisor.run(stop_event))
    await asyncio.wait_for(started.wait(), timeout=ASYNC_TEST_TIMEOUT_SECONDS)
    stop_event.set()
    await asyncio.wait_for(task, timeout=ASYNC_TEST_TIMEOUT_SECONDS)

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
        pipeline_factory=lambda _safety_check: Pipeline(),
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        fencing_wait=instant_fencing,
    )
    task = asyncio.create_task(supervisor.run(asyncio.Event()))
    await asyncio.wait_for(started.wait(), timeout=ASYNC_TEST_TIMEOUT_SECONDS)
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
        pipeline_factory=lambda _safety_check: StuckPipeline(),
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        hard_stop=hard_stop,
        fencing_wait=instant_fencing,
    )
    task = asyncio.create_task(supervisor.run(stop_event))
    await asyncio.wait_for(started.wait(), timeout=ASYNC_TEST_TIMEOUT_SECONDS)
    stop_event.set()
    with pytest.raises(CommunicationRuntimeShutdownTimeout):
        await asyncio.wait_for(task, timeout=ASYNC_TEST_TIMEOUT_SECONDS)
    await asyncio.sleep(0)
    assert events == ["hard-stop"]


@pytest.mark.asyncio
async def test_provider_close_retries_before_releasing_reference(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)

    class RetryCloseProvider(FakeProvider):
        def __init__(self):
            super().__init__([])
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1
            if self.close_calls == 1:
                await asyncio.Event().wait()

    provider = RetryCloseProvider()

    async def dispatch(_session, *, dispatcher_id, scope):
        assert dispatcher_id == "test-runtime"
        assert scope.mode == "all"
        return None

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(provider_close_seconds=0.01),
        session_factory=runtime_session_factory,
        provider_factory=lambda: provider,
        safety_check=allow_safety,
        worker_factory=lambda _provider, _scope: FakeWorker([], outcome="idle"),
        dispatch=dispatch,
    )
    await pipeline.run_cycle()
    await pipeline.close()

    assert provider.close_calls == 2
    assert pipeline._provider is None


@pytest.mark.asyncio
async def test_persistent_provider_close_failure_fail_stops_without_unlock(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)
    events = []
    worker_started = asyncio.Event()
    release_close = asyncio.Event()

    class OrderedLock(RuntimeLock):
        async def release(self):
            events.append("lock-release")
            await super().release()

    class PersistentProvider(FakeProvider):
        def __init__(self):
            super().__init__(events)
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1
            while not release_close.is_set():
                try:
                    await release_close.wait()
                except asyncio.CancelledError:
                    # Model a provider resource that ignores cancellation.
                    continue

    class StartedWorker(FakeWorker):
        async def run_once(self):
            worker_started.set()
            return DeliveryRunOutcome(outcome="idle")

    provider = PersistentProvider()
    pipeline_holder = []

    async def dispatch(_session, *, dispatcher_id, scope):
        assert dispatcher_id == "test-runtime"
        assert scope.mode == "all"
        return None

    def pipeline_factory(safety_check):
        pipeline = CommunicationRuntimePipeline(
            config=runtime_config(provider_close_seconds=0.01),
            session_factory=runtime_session_factory,
            provider_factory=lambda: provider,
            safety_check=safety_check,
            worker_factory=lambda _provider, _scope: StartedWorker(events),
            dispatch=dispatch,
        )
        pipeline_holder.append(pipeline)
        return pipeline

    def hard_stop():
        events.append("hard-stop")
        release_close.set()

    AcquiredLockService.lock = OrderedLock("mvn:test", None, True, "acquired")
    stop_event = asyncio.Event()
    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(provider_close_seconds=0.01),
        session_factory=runtime_session_factory,
        pipeline_factory=pipeline_factory,
        lock_service=AcquiredLockService,
        primary_probe=lambda _factory: asyncio.sleep(0),
        hard_stop=hard_stop,
        fencing_wait=instant_fencing,
    )
    task = asyncio.create_task(supervisor.run(stop_event))
    await asyncio.wait_for(
        worker_started.wait(),
        timeout=ASYNC_TEST_TIMEOUT_SECONDS,
    )
    stop_event.set()

    with pytest.raises(CommunicationRuntimeShutdownTimeout):
        await asyncio.wait_for(task, timeout=ASYNC_TEST_TIMEOUT_SECONDS)
    await asyncio.sleep(0)
    assert provider.close_calls == 1
    assert pipeline_holder[0]._provider is provider
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
        pipeline_factory=lambda _safety_check: (_ for _ in ()).throw(
            AssertionError()
        ),
        lock_service=AcquiredLockService,
        primary_probe=reject,
        fencing_wait=instant_fencing,
    )
    with pytest.raises(CommunicationRuntimePrimaryRequired):
        await supervisor.run(asyncio.Event())
    assert events == ["lock-release"]


@pytest.mark.asyncio
async def test_writable_probe_rejects_sqlite(runtime_session_factory):
    with pytest.raises(CommunicationRuntimePrimaryRequired, match="PostgreSQL"):
        await assert_primary_writable(runtime_session_factory)


@pytest.mark.asyncio
async def test_runtime_statement_error_logs_never_emit_pii_marker(
    tmp_path,
    caplog,
    capsys,
):
    marker = "PII-MARKER-375291112233"
    log_path = tmp_path / "runtime-privacy.log"
    stream = io.StringIO()
    runtime_logger = logging.getLogger("services.communications.runtime_supervisor")
    lock_logger = logging.getLogger("services.runtime_lock_service")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    stream_handler = logging.StreamHandler(stream)
    runtime_logger.addHandler(file_handler)
    runtime_logger.addHandler(stream_handler)
    lock_logger.addHandler(file_handler)
    lock_logger.addHandler(stream_handler)
    caplog.set_level(logging.ERROR, logger=runtime_logger.name)
    caplog.set_level(logging.ERROR, logger=lock_logger.name)

    def failing_session_factory():
        raise StatementError(
            f"database failure {marker}",
            f"SELECT '{marker}'",
            {"phone": marker},
            RuntimeError(marker),
        )

    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=failing_session_factory,
        pipeline_factory=lambda _safety_check: (_ for _ in ()).throw(
            AssertionError()
        ),
        fencing_wait=instant_fencing,
    )

    class FailingLockConnection:
        closed = False

        async def execute(self, *_args, **_kwargs):
            raise StatementError(
                f"lock failure {marker}",
                f"SELECT '{marker}'",
                {"phone": marker},
                RuntimeError(marker),
            )

        async def invalidate(self):
            return None

        async def close(self):
            self.closed = True

    try:
        await supervisor._best_effort_status(CommunicationRuntimeStatus.FAULTED)
        runtime_lock = RuntimeLock(
            "mvn:test:privacy",
            FailingLockConnection(),
            True,
            "acquired",
        )
        assert await runtime_lock.is_held() is False
        file_handler.flush()
        captured = capsys.readouterr()
        combined_logs = "\n".join(
            (
                caplog.text,
                stream.getvalue(),
                log_path.read_text(encoding="utf-8"),
                captured.out,
                captured.err,
            )
        )
    finally:
        runtime_logger.removeHandler(file_handler)
        runtime_logger.removeHandler(stream_handler)
        lock_logger.removeHandler(file_handler)
        lock_logger.removeHandler(stream_handler)
        file_handler.close()
        stream_handler.close()

    assert marker not in combined_logs
    assert "error_code=runtime_state_write_failed" in combined_logs
    assert "error_code=runtime_lock_liveness_failed" in combined_logs
    assert "error_type=StatementError" in combined_logs
