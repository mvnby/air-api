import json
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from aiogram.fsm.storage.memory import DataNotDictLikeError

from .api_runtime import get_bot_api_gateway


class ApiFsmStorage(BaseStorage):
    def __init__(self, gateway_factory=get_bot_api_gateway) -> None:
        self.gateway_factory = gateway_factory

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

    async def _upsert(
        self,
        key: StorageKey,
        *,
        state: str | None | object = ...,
        data: dict[str, Any] | object = ...,
    ) -> None:
        await self.gateway_factory().update_fsm_state(
            storage_key=self.build_storage_key(key),
            bot_id=key.bot_id,
            chat_id=key.chat_id,
            user_id=key.user_id,
            thread_id=key.thread_id,
            business_connection_id=key.business_connection_id,
            destiny=key.destiny,
            write_state=state is not ...,
            state=None if state is ... else state,
            write_data=data is not ...,
            data={} if data is ... else data,
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._upsert(key, state=self._state_value(state))

    async def get_state(self, key: StorageKey) -> str | None:
        result = await self.gateway_factory().get_fsm_state(
            storage_key=self.build_storage_key(key)
        )
        return result.state

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(key, data=self._json_safe_data(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        result = await self.gateway_factory().get_fsm_state(
            storage_key=self.build_storage_key(key)
        )
        return dict(result.data)

    async def close(self) -> None:
        pass
