from unittest.mock import AsyncMock

import pytest

from bot_app.keyboards import quick_order_confirm_keyboard
from services.bot_service import BotService


class _FakeResponse:
    def __init__(self, payload=None, *, raise_error: Exception | None = None):
        self._payload = payload or {"ok": True}
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error

    def json(self):
        return self._payload


class _FakeAsyncClient:
    requests = []
    response = _FakeResponse()

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, json):
        self.__class__.requests.append({"url": url, "json": json})
        return self.__class__.response


@pytest.mark.asyncio
async def test_send_rich_message_calls_telegram_bot_api(monkeypatch):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse({"ok": True, "result": {"message_id": 1}})
    monkeypatch.setattr("services.bot_service.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)
    fallback = AsyncMock()
    monkeypatch.setattr(BotService, "send_message", fallback)

    delivered = await BotService.send_rich_message(777, "<h3>Заказ</h3>", fallback_text="fallback")

    assert delivered is True
    assert _FakeAsyncClient.requests == [
        {
            "url": "https://api.telegram.org/bot123:test/sendRichMessage",
            "json": {
                "chat_id": 777,
                "rich_message": {
                    "html": "<h3>Заказ</h3>",
                },
            },
        }
    ]
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_rich_message_serializes_reply_markup(monkeypatch):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse({"ok": True, "result": {"message_id": 1}})
    monkeypatch.setattr("services.bot_service.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)

    delivered = await BotService.send_rich_message(
        777,
        "<h3>Черновик</h3>",
        reply_markup=quick_order_confirm_keyboard(),
    )

    assert delivered is True
    payload = _FakeAsyncClient.requests[0]["json"]
    assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "Создать"
    assert payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "quick_order_create"


@pytest.mark.asyncio
async def test_send_rich_message_falls_back_to_html_message(monkeypatch):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse({"ok": False})
    monkeypatch.setattr("services.bot_service.httpx.AsyncClient", _FakeAsyncClient)
    fallback = AsyncMock()
    monkeypatch.setattr(BotService, "send_message", fallback)

    delivered = await BotService.send_rich_message(777, "<h3>Заказ</h3>", fallback_text="fallback")

    assert delivered is False
    fallback.assert_awaited_once_with(777, "fallback", reply_markup=None)
