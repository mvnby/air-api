from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationRuntimeState
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_state import (
    CommunicationRuntimeControlConflict,
    CommunicationRuntimeMode,
    CommunicationRuntimeModeBlocked,
    CommunicationRuntimeStateOwnershipLost,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"
RUN_ID_B = "123e4567-e89b-42d3-a456-426614174001"


def test_control_application_cannot_remove_or_move_an_existing_watermark():
    watermark = datetime(2026, 7, 27, tzinfo=timezone.utc)
    state = CommunicationRuntimeState(
        channel="telegram",
        installation_estimate_watermark_at=watermark,
    )

    for replacement in (None, watermark + timedelta(seconds=1)):
        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="installation_activation_watermark_immutable",
        ):
            CommunicationRuntimeStateService._apply_control(
                state,
                mode=CommunicationRuntimeMode.OFF,
                canary_run_id=None,
                now=watermark,
                installation_estimate_watermark_at=replacement,
            )
        assert state.control_revision == 0
        assert state.installation_estimate_watermark_at == watermark


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


@pytest.mark.asyncio
async def test_mode_is_operator_owned_and_heartbeats_do_not_enable_runtime(
    runtime_session_factory,
):
    async with runtime_session_factory() as session:
        initial = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        await session.commit()
        assert initial.mode == "off"
        assert initial.canary_run_id is None
        assert initial.control_revision == 0
        assert initial.status == "stopped"

    async with runtime_session_factory() as session:
        canary = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=RUN_ID_A,
        )
        assert canary.canary_run_id == RUN_ID_A
        assert canary.control_revision == 1
        idempotent = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=RUN_ID_A,
        )
        assert idempotent.control_revision == 1
        await session.commit()
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="worker-a",
        )
        await CommunicationRuntimeStateService.record_status(
            session,
            channel="telegram",
            instance_id="worker-a",
            status=CommunicationRuntimeStatus.PAUSED,
            last_error_code="operator_pause",
            activity=True,
        )
        await session.commit()

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.mode == "canary"
        assert state.canary_run_id == RUN_ID_A
        assert state.control_revision == 1
        assert state.status == "paused"
        assert state.instance_id == "worker-a"
        assert state.started_at is not None
        assert state.heartbeat_at is not None
        assert state.last_activity_at is not None
        assert state.heartbeat_at.tzinfo in (None, timezone.utc)
        assert state.last_error_code == "operator_pause"


@pytest.mark.asyncio
async def test_control_transitions_are_explicit_and_revisioned(
    runtime_session_factory,
):
    async with runtime_session_factory() as session:
        with pytest.raises(ValueError, match="requires a run ID"):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.CANARY,
            )
        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="installation_activation_requires_typed_control",
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.ALL,
                canary_run_id=RUN_ID_A,
            )

        canary = await CommunicationRuntimeStateService.arm_canary_from_off(
            session,
            channel="telegram",
            run_id=RUN_ID_A,
        )
        assert canary.control_revision == 1

        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="installation_activation_requires_typed_control",
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.ALL,
            )
        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="runtime_control_transition_requires_off",
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.CANARY,
                canary_run_id=RUN_ID_B,
            )

        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="canary_runtime_not_off",
        ):
            await CommunicationRuntimeStateService.arm_canary_from_off(
                session,
                channel="telegram",
                run_id=RUN_ID_B,
            )

        off = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        assert off.canary_run_id is None
        assert off.control_revision == 2
        with pytest.raises(
            CommunicationRuntimeControlConflict,
            match="installation_activation_requires_typed_control",
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.ALL,
            )
        assert off.control_revision == 2
        await session.commit()


@pytest.mark.asyncio
async def test_scope_revision_fences_fast_canary_rearm(
    runtime_session_factory,
):
    async with runtime_session_factory() as session:
        first = await CommunicationRuntimeStateService.arm_canary_from_off(
            session,
            channel="telegram",
            run_id=RUN_ID_A,
        )
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="worker-a",
        )
        stale_scope = CommunicationProcessingScope.canary(
            run_id=RUN_ID_A,
            control_revision=first.control_revision,
        )
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        rearmed = await CommunicationRuntimeStateService.arm_canary_from_off(
            session,
            channel="telegram",
            run_id=RUN_ID_A,
        )
        assert rearmed.control_revision == first.control_revision + 2

        with pytest.raises(CommunicationRuntimeModeBlocked) as blocked:
            await CommunicationRuntimeStateService.assert_owned_processing_scope(
                session,
                channel="telegram",
                instance_id="worker-a",
                scope=stale_scope,
            )
        assert blocked.value.mode == CommunicationRuntimeMode.CANARY
        assert blocked.value.canary_run_id == RUN_ID_A
        assert blocked.value.control_revision == rearmed.control_revision

        current_scope = CommunicationProcessingScope.canary(
            run_id=RUN_ID_A,
            control_revision=rearmed.control_revision,
        )
        current = (
            await CommunicationRuntimeStateService.assert_owned_processing_scope(
                session,
                channel="telegram",
                instance_id="worker-a",
                scope=current_scope,
            )
        )
        assert current.control_revision == rearmed.control_revision


@pytest.mark.asyncio
async def test_replacement_instance_fences_stale_lifecycle_writer(
    runtime_session_factory,
):
    async with runtime_session_factory() as session:
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="worker-a",
        )
        await session.commit()
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="worker-b",
        )
        await session.commit()

    async with runtime_session_factory() as session:
        with pytest.raises(CommunicationRuntimeStateOwnershipLost):
            await CommunicationRuntimeStateService.record_status(
                session,
                channel="telegram",
                instance_id="worker-a",
                status=CommunicationRuntimeStatus.RUNNING,
            )
        await session.rollback()
        control = await CommunicationRuntimeStateService.read_owned_control(
            session,
            channel="telegram",
            instance_id="worker-b",
        )
        assert control.instance_id == "worker-b"
        assert control.status == CommunicationRuntimeStatus.FENCING
