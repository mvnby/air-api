from dataclasses import replace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationRuntimeState
from services.communications.delivery_worker import DeliveryRunOutcome
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime import (
    CommunicationRuntimeConfig,
    CommunicationRuntimePipeline,
)
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
)


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"
RUN_ID_B = "123e4567-e89b-42d3-a456-426614174001"


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


async def allow_safety(_scope: CommunicationProcessingScope) -> None:
    return None


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


class FakeWorker:
    def __init__(self, events):
        self.events = events

    async def run_once(self):
        self.events.append("delivery")
        return DeliveryRunOutcome(outcome="idle")


@pytest.mark.asyncio
async def test_off_mode_never_constructs_provider(runtime_session_factory):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.OFF)

    def provider_factory():
        raise AssertionError("provider must remain dormant")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=allow_safety,
    )
    assert await pipeline.run_cycle() is False
    await pipeline.close()

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.status == "disabled"
        assert state.last_error_code is None


@pytest.mark.asyncio
async def test_all_mode_is_dormant_without_immutable_allow_gate(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.ALL)

    def provider_factory():
        raise AssertionError("provider must remain dormant")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(allow_all_mode=False),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=allow_safety,
    )
    assert await pipeline.run_cycle() is False
    await pipeline.close()

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.status == "paused"
        assert state.last_error_code == "all_mode_not_enabled"


@pytest.mark.asyncio
async def test_corrupt_canary_run_id_fails_closed_before_provider(
    runtime_session_factory,
):
    await own_mode(runtime_session_factory, CommunicationRuntimeMode.OFF)
    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        state.mode = CommunicationRuntimeMode.CANARY.value
        state.canary_run_id = "x" * 36
        state.control_revision += 1
        await session.commit()

    def provider_factory():
        raise AssertionError("provider must remain dormant")

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(allow_all_mode=False),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=allow_safety,
    )
    assert await pipeline.run_cycle() is False

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.status == "paused"
        assert state.last_error_code == "canary_scope_invalid"


@pytest.mark.asyncio
async def test_valid_canary_scope_processes_and_scope_change_resets_cache(
    runtime_session_factory,
):
    first_control = await own_mode(
        runtime_session_factory,
        CommunicationRuntimeMode.CANARY,
        canary_run_id=RUN_ID_A,
    )
    events: list[object] = []
    provider_count = 0

    class NumberedProvider(FakeProvider):
        def __init__(self, number):
            super().__init__(events)
            self.number = number

        async def close(self):
            events.append(("provider-close", self.number))

    def provider_factory():
        nonlocal provider_count
        provider_count += 1
        events.append(("provider-create", provider_count))
        return NumberedProvider(provider_count)

    async def safety_check(scope):
        events.append(("safety", scope.canary_run_id, scope.control_revision))

    async def dispatch(_session, *, dispatcher_id, scope):
        assert dispatcher_id == "test-runtime"
        events.append(("dispatch", scope.canary_run_id, scope.control_revision))
        return None

    def worker_factory(provider, scope):
        events.append(("worker", provider.number, scope))
        return FakeWorker(events)

    pipeline = CommunicationRuntimePipeline(
        config=runtime_config(allow_all_mode=False),
        session_factory=runtime_session_factory,
        provider_factory=provider_factory,
        safety_check=safety_check,
        worker_factory=worker_factory,
        dispatch=dispatch,
    )
    assert await pipeline.run_cycle() is False

    async with runtime_session_factory() as session:
        off = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        second = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=RUN_ID_B,
        )
        await session.commit()
    assert off.control_revision == first_control.control_revision + 1
    assert second.control_revision == first_control.control_revision + 2

    assert await pipeline.run_cycle() is False
    assert provider_count == 2
    worker_events = [event for event in events if event[0] == "worker"]
    assert len(worker_events) == 2
    assert worker_events[0][2] == CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=first_control.control_revision,
    )
    assert worker_events[1][2] == CommunicationProcessingScope.canary(
        run_id=RUN_ID_B,
        control_revision=second.control_revision,
    )
    assert events.index(("provider-close", 1)) < events.index(
        ("provider-create", 2)
    )
    await pipeline.close()
