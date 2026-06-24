from pathlib import Path

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import DataNotDictLikeError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from bot_app.fsm_storage import SqlAlchemyFsmStorage
from models import BotFsmState


@pytest.fixture
async def sqlite_fsm_session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot_fsm.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


def _storage_key() -> StorageKey:
    return StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, destiny="staff")


def test_sqlalchemy_fsm_storage_key_is_collision_resistant():
    first = StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, business_connection_id="a:b", destiny="staff")
    second = StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, business_connection_id="a", destiny="b:staff")

    assert SqlAlchemyFsmStorage.build_storage_key(first) != SqlAlchemyFsmStorage.build_storage_key(second)


@pytest.mark.asyncio
async def test_sqlalchemy_fsm_storage_persists_state_and_data(sqlite_fsm_session_factory):
    storage = SqlAlchemyFsmStorage(session_factory=sqlite_fsm_session_factory)
    key = _storage_key()

    await storage.set_state(key, "ShopState:waiting_for_quick_order")
    await storage.set_data(key, {"draft": {"phone": "+375291234567"}, "attempt": 1})

    reloaded = SqlAlchemyFsmStorage(session_factory=sqlite_fsm_session_factory)
    assert await reloaded.get_state(key) == "ShopState:waiting_for_quick_order"
    assert await reloaded.get_data(key) == {"draft": {"phone": "+375291234567"}, "attempt": 1}


@pytest.mark.asyncio
async def test_sqlalchemy_fsm_storage_deletes_empty_records(sqlite_fsm_session_factory):
    storage = SqlAlchemyFsmStorage(session_factory=sqlite_fsm_session_factory)
    key = _storage_key()

    await storage.set_state(key, "ShopState:waiting_for_selection")
    await storage.set_data(key, {"query": "7"})
    await storage.set_state(key, None)
    assert await storage.get_data(key) == {"query": "7"}

    await storage.set_data(key, {})
    assert await storage.get_state(key) is None
    assert await storage.get_data(key) == {}

    async with sqlite_fsm_session_factory() as session:
        rows = (await session.execute(select(BotFsmState))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_sqlalchemy_fsm_storage_rejects_non_dict_data(sqlite_fsm_session_factory):
    storage = SqlAlchemyFsmStorage(session_factory=sqlite_fsm_session_factory)

    with pytest.raises(DataNotDictLikeError):
        await storage.set_data(_storage_key(), [("bad", "shape")])  # type: ignore[arg-type]
