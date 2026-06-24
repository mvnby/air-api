import json
from datetime import datetime
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from aiogram.fsm.storage.memory import DataNotDictLikeError

from core.database import async_session_maker
from models import BotFsmState


class SqlAlchemyFsmStorage(BaseStorage):
    def __init__(self, session_factory=async_session_maker) -> None:
        self.session_factory = session_factory

    @staticmethod
    def build_storage_key(key: StorageKey) -> str:
        parts = [
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id if key.thread_id is not None else "",
            key.business_connection_id or "",
            key.destiny or "default",
        ]
        return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _state_value(state: StateType = None) -> str | None:
        return state.state if isinstance(state, State) else state

    @staticmethod
    def _json_safe_data(data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)
        return json.loads(json.dumps(data, ensure_ascii=False, default=str))

    async def _upsert(self, key: StorageKey, *, state: str | None | object = ..., data: dict[str, Any] | object = ...) -> None:
        storage_key = self.build_storage_key(key)
        async with self.session_factory() as session:
            row = await session.get(BotFsmState, storage_key)
            if row is None:
                row = BotFsmState(
                    storage_key=storage_key,
                    bot_id=key.bot_id,
                    chat_id=key.chat_id,
                    user_id=key.user_id,
                    thread_id=key.thread_id,
                    business_connection_id=key.business_connection_id,
                    destiny=key.destiny,
                )

            if state is not ...:
                row.state = state
            if data is not ...:
                row.data = data
            row.updated_at = datetime.now()

            if row.state is None and not row.data:
                if await session.get(BotFsmState, storage_key):
                    await session.delete(row)
            else:
                session.add(row)
            await session.commit()

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._upsert(key, state=self._state_value(state))

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.session_factory() as session:
            row = await session.get(BotFsmState, self.build_storage_key(key))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(key, data=self._json_safe_data(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = await session.get(BotFsmState, self.build_storage_key(key))
            return dict(row.data or {}) if row else {}

    async def close(self) -> None:
        pass
