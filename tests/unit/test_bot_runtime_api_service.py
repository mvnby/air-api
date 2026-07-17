from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import BotFsmState, BotRuntimeLease
from services.bot_runtime_api_service import BotRuntimeApiService


@pytest.fixture
async def runtime_session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(BotFsmState.__table__.create)
        await connection.run_sync(BotRuntimeLease.__table__.create)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_service_preserves_partial_fsm_updates(runtime_session_factory):
    async with runtime_session_factory() as session:
        await BotRuntimeApiService.update_fsm_state(
            session,
            storage_key="key",
            bot_id=1,
            chat_id=2,
            user_id=3,
            thread_id=None,
            business_connection_id=None,
            destiny="default",
            write_state=True,
            state="waiting",
            write_data=False,
            data={},
        )
    async with runtime_session_factory() as session:
        result = await BotRuntimeApiService.update_fsm_state(
            session,
            storage_key="key",
            bot_id=1,
            chat_id=2,
            user_id=3,
            thread_id=None,
            business_connection_id=None,
            destiny="default",
            write_state=False,
            state=None,
            write_data=True,
            data={"draft": 7},
        )
    assert result == {"state": "waiting", "data": {"draft": 7}}


@pytest.mark.asyncio
async def test_runtime_service_lease_has_single_owner_and_explicit_release(runtime_session_factory):
    async with runtime_session_factory() as session:
        first = await BotRuntimeApiService.acquire_lease(
            session, name="bot", owner_id="first", ttl_seconds=45
        )
    async with runtime_session_factory() as session:
        second = await BotRuntimeApiService.acquire_lease(
            session, name="bot", owner_id="second", ttl_seconds=45
        )
    assert first["acquired"] is True
    assert second["acquired"] is False

    async with runtime_session_factory() as session:
        assert await BotRuntimeApiService.release_lease(
            session, name="bot", owner_id="first"
        )
    async with runtime_session_factory() as session:
        takeover = await BotRuntimeApiService.acquire_lease(
            session, name="bot", owner_id="second", ttl_seconds=45
        )
    assert takeover["acquired"] is True
