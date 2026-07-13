from datetime import timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationRuntimeState
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateOwnershipLost,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)


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
        assert initial.status == "stopped"

    async with runtime_session_factory() as session:
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.CANARY,
        )
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
            last_error_code="canary_scope_unconfigured",
            activity=True,
        )
        await session.commit()

    async with runtime_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.mode == "canary"
        assert state.status == "paused"
        assert state.instance_id == "worker-a"
        assert state.started_at is not None
        assert state.heartbeat_at is not None
        assert state.last_activity_at is not None
        assert state.heartbeat_at.tzinfo in (None, timezone.utc)
        assert state.last_error_code == "canary_scope_unconfigured"


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
