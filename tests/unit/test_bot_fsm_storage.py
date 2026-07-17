import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import DataNotDictLikeError

from api_contracts.bot import BotFsmStateResponse
from bot_app.fsm_storage import ApiFsmStorage


class FakeFsmGateway:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def get_fsm_state(self, *, storage_key: str) -> BotFsmStateResponse:
        row = self.rows.get(storage_key, {"state": None, "data": {}})
        return BotFsmStateResponse.model_validate(row)

    async def update_fsm_state(self, **payload) -> BotFsmStateResponse:
        key = payload["storage_key"]
        row = dict(self.rows.get(key, {"state": None, "data": {}}))
        if payload["write_state"]:
            row["state"] = payload["state"]
        if payload["write_data"]:
            row["data"] = payload["data"]
        if row["state"] is None and not row["data"]:
            self.rows.pop(key, None)
        else:
            self.rows[key] = row
        return BotFsmStateResponse.model_validate(row)


def _storage_key() -> StorageKey:
    return StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, destiny="staff")


def test_api_fsm_storage_key_is_collision_resistant():
    first = StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, business_connection_id="a:b", destiny="staff")
    second = StorageKey(bot_id=1, chat_id=2, user_id=3, thread_id=4, business_connection_id="a", destiny="b:staff")
    assert ApiFsmStorage.build_storage_key(first) != ApiFsmStorage.build_storage_key(second)


@pytest.mark.asyncio
async def test_api_fsm_storage_persists_state_and_data_across_instances():
    gateway = FakeFsmGateway()
    storage = ApiFsmStorage(gateway_factory=lambda: gateway)
    key = _storage_key()

    await storage.set_state(key, "ShopState:waiting_for_quick_order")
    await storage.set_data(key, {"draft": {"phone": "+375291234567"}, "attempt": 1})

    reloaded = ApiFsmStorage(gateway_factory=lambda: gateway)
    assert await reloaded.get_state(key) == "ShopState:waiting_for_quick_order"
    assert await reloaded.get_data(key) == {"draft": {"phone": "+375291234567"}, "attempt": 1}


@pytest.mark.asyncio
async def test_api_fsm_storage_deletes_empty_records():
    gateway = FakeFsmGateway()
    storage = ApiFsmStorage(gateway_factory=lambda: gateway)
    key = _storage_key()

    await storage.set_state(key, "ShopState:waiting_for_selection")
    await storage.set_data(key, {"query": "7"})
    await storage.set_state(key, None)
    assert await storage.get_data(key) == {"query": "7"}
    await storage.set_data(key, {})
    assert gateway.rows == {}


@pytest.mark.asyncio
async def test_api_fsm_storage_rejects_non_dict_data():
    storage = ApiFsmStorage(gateway_factory=FakeFsmGateway)
    with pytest.raises(DataNotDictLikeError):
        await storage.set_data(_storage_key(), [("bad", "shape")])  # type: ignore[arg-type]
