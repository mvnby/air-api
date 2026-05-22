from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot_app.handlers import admin as admin_handler


class _DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.answer = AsyncMock()
        self.delete = AsyncMock()


class _DummyState:
    def __init__(self, data: dict):
        self._data = data
        self.clear = AsyncMock()

    async def get_data(self):
        return self._data


class _DummyCallback:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _DummyMessage(text="")
        self.answer = AsyncMock()


class _DummySessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_async_session_maker():
    return _DummySessionContext()


def test_admin_handler_has_no_direct_dao_import():
    source = Path("bot_app/handlers/admin.py").read_text(encoding="utf-8")
    assert "from crud.product import ProductDAO" not in source
    assert "from services.product_service import ProductService" in source


@pytest.mark.asyncio
async def test_edit_price_finish_calls_service(monkeypatch):
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "update_price", service_mock)

    msg = _DummyMessage(text="12345")
    state = _DummyState({"product_id": "7"})
    await admin_handler.edit_price_finish(msg, state)

    service_mock.assert_awaited_once()
    msg.answer.assert_awaited_with("✅ Цена обновлена.")
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_uses_callback_answer(monkeypatch):
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.settings, "ADMIN_ID", 0, raising=False)
    monkeypatch.setattr(admin_handler.settings, "ADMIN_IDS", "1,2", raising=False)
    service_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_confirm_10", user_id=2)
    await admin_handler.delete_item(callback)

    service_mock.assert_awaited_once()
    callback.answer.assert_awaited_with("Товар не найден", show_alert=True)
