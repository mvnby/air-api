import asyncio
from dataclasses import replace
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationRuntimeState
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.delivery_worker import DeliveryRunOutcome
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime import (
    CommunicationRuntimeConfig,
    CommunicationRuntimePipeline,
    CommunicationRuntimeSupervisor,
)
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeModeBlocked,
    CommunicationRuntimeStateService,
)
from services.runtime_lock_service import RuntimeLock


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"


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
        db_probe_timeout_seconds=0.1,
        fencing_seconds=2,
        shutdown_seconds=0.2,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=30,
    )
    return replace(config, **overrides)


async def own_mode(session_factory, mode: CommunicationRuntimeMode):
    async with session_factory() as session:
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        assert mode == CommunicationRuntimeMode.ALL
        state.mode = CommunicationRuntimeMode.ALL.value
        state.canary_run_id = None
        state.control_revision = int(state.control_revision) + 1
        state.installation_estimate_watermark_at = (
            state.installation_estimate_watermark_at
            or datetime(2000, 1, 1, tzinfo=timezone.utc)
        )
        session.add(state)
        await session.flush()
        control = CommunicationRuntimeStateService._to_control(state)
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="test-runtime",
        )
        await session.commit()
        return CommunicationProcessingScope.all(
            control_revision=control.control_revision,
            event_created_at_watermark=(
                control.installation_estimate_watermark_at
            ),
        )


async def set_mode(session_factory, mode: CommunicationRuntimeMode) -> None:
    async with session_factory() as session:
        current = await CommunicationRuntimeStateService.read_control(
            session,
            channel="telegram",
        )
        if (
            current.mode != CommunicationRuntimeMode.OFF
            and mode != CommunicationRuntimeMode.OFF
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.OFF,
            )
        if mode == CommunicationRuntimeMode.ALL:
            state = await CommunicationRuntimeStateService._lock_state(
                session,
                channel="telegram",
            )
            state.mode = CommunicationRuntimeMode.ALL.value
            state.canary_run_id = None
            state.control_revision = int(state.control_revision) + 1
            state.installation_estimate_watermark_at = (
                state.installation_estimate_watermark_at
                or datetime(2000, 1, 1, tzinfo=timezone.utc)
            )
            session.add(state)
        else:
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=mode,
                canary_run_id=(
                    RUN_ID_A if mode == CommunicationRuntimeMode.CANARY else None
                ),
            )
        await session.commit()


class ForbiddenProvider:
    channel = "telegram"

    async def send(self, **_kwargs):
        raise AssertionError("provider send must not be called")

    async def close(self):
        return None


class IdleWorker:
    async def run_once(self):
        return DeliveryRunOutcome(outcome="idle")


@pytest.mark.parametrize("invalid_lease", [15, 29])
def test_runtime_rejects_lease_below_delivery_service_minimum(invalid_lease):
    with pytest.raises(ValueError, match="between 30 and 3600"):
        runtime_config(lease_seconds=invalid_lease)


def test_runtime_lease_matches_delivery_service_bounds():
    assert CommunicationDeliveryService.MIN_LEASE_SECONDS == 30
    assert runtime_config(lease_seconds=30).lease_seconds == 30
    assert runtime_config(lease_seconds=90).lease_seconds == 90


def test_runtime_rejects_lease_that_cannot_cover_bounded_delivery_window():
    with pytest.raises(ValueError, match="strictly greater"):
        runtime_config(
            db_probe_timeout_seconds=5,
            provider_timeout_seconds=10,
            fencing_seconds=100,
            lease_seconds=45,
        )
    assert runtime_config(
        db_probe_timeout_seconds=5,
        provider_timeout_seconds=10,
        fencing_seconds=100,
        lease_seconds=46,
    ).lease_seconds == 46


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("blocked_mode", "expected_status", "expected_error"),
    [
        (CommunicationRuntimeMode.OFF, "disabled", None),
        (
            CommunicationRuntimeMode.CANARY,
            "paused",
            "control_scope_changed",
        ),
    ],
)
async def test_db_mode_flip_before_dispatch_aborts_cycle(
    runtime_session_factory,
    blocked_mode,
    expected_status,
    expected_error,
):
    original_scope = await own_mode(
        runtime_session_factory,
        CommunicationRuntimeMode.ALL,
    )
    events = []
    safety_calls = 0

    async def safety_check(scope):
        nonlocal safety_calls
        safety_calls += 1
        async with runtime_session_factory() as session:
            await CommunicationRuntimeStateService.assert_owned_processing_scope(
                session,
                channel="telegram",
                instance_id="test-runtime",
                scope=scope,
            )
        if safety_calls == 1:
            await set_mode(runtime_session_factory, blocked_mode)

    async def dispatch(_session, *, dispatcher_id, scope):
        assert scope.mode == "all"
        events.append(("dispatch", dispatcher_id))

    def provider_factory():
        events.append(("provider", None))
        return ForbiddenProvider()

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=safety_check,
        worker_factory=lambda _provider, _scope: IdleWorker(),
        dispatch=dispatch,
    )

    assert await pipeline.run_cycle() is False
    assert events == []
    assert original_scope.control_revision == 1
    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.status == expected_status
        assert state.last_error_code == expected_error

    await set_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)
    assert await pipeline.run_cycle() is False
    assert events == [
        ("dispatch", "test-runtime"),
        ("provider", None),
    ]
    await pipeline.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_mode",
    [CommunicationRuntimeMode.OFF, CommunicationRuntimeMode.CANARY],
)
async def test_supervisor_action_fence_rechecks_active_db_mode(
    runtime_session_factory,
    blocked_mode,
):
    stale_scope = await own_mode(
        runtime_session_factory,
        CommunicationRuntimeMode.ALL,
    )
    await set_mode(runtime_session_factory, blocked_mode)
    supervisor = CommunicationRuntimeSupervisor(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        pipeline_factory=lambda _safety_check: (_ for _ in ()).throw(
            AssertionError()
        ),
        primary_probe=lambda _factory: asyncio.sleep(0),
    )
    runtime_lock = RuntimeLock("mvn:test", None, True, "acquired")

    with pytest.raises(CommunicationRuntimeModeBlocked) as blocked:
        await supervisor._assert_safe_to_work(
            asyncio.Event(),
            runtime_lock,
            stale_scope,
        )
    assert blocked.value.mode == blocked_mode
    assert blocked.value.control_revision > stale_scope.control_revision
