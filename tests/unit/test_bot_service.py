from unittest.mock import AsyncMock

import pytest

from bot_app.keyboards import quick_order_confirm_keyboard
from services.bot_service import BotService


class _FakeResponse:
    def __init__(self, payload=None, *, raise_error: Exception | None = None, status_code: int = 200):
        self._payload = payload or {"ok": True}
        self._raise_error = raise_error
        self.status = status_code

    async def __aenter__(self):
        if self._raise_error:
            raise self._raise_error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, *, content_type=None):
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

    def post(self, url, *, json):
        self.__class__.requests.append({"url": url, "json": json})
        return self.__class__.response


class _FakeBot:
    sent = []
    error: Exception | None = None

    def __init__(self, *, token):
        self.token = token

    def context(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send_message(self, **kwargs):
        if self.__class__.error:
            raise self.__class__.error
        self.__class__.sent.append(kwargs)


@pytest.mark.asyncio
async def test_send_message_returns_true_only_after_confirmed_send(monkeypatch):
    _FakeBot.sent = []
    _FakeBot.error = None
    monkeypatch.setattr("services.bot_service.Bot", _FakeBot)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)

    delivered = await BotService.send_message(777, "<b>Заказ</b>")

    assert delivered is True
    assert _FakeBot.sent == [
        {
            "chat_id": 777,
            "text": "<b>Заказ</b>",
            "parse_mode": "HTML",
            "reply_markup": None,
        }
    ]


@pytest.mark.asyncio
async def test_send_message_returns_false_without_token_or_after_error(monkeypatch, caplog):
    _FakeBot.sent = []
    monkeypatch.setattr("services.bot_service.Bot", _FakeBot)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "", raising=False)

    assert await BotService.send_message(777, "message") is False

    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:secret-token", raising=False)
    _FakeBot.error = RuntimeError("https://api.telegram.org/bot123:secret-token/sendMessage")
    with caplog.at_level("ERROR"):
        assert await BotService.send_message(777, "message") is False

    assert "123:secret-token" not in caplog.text
    assert "api.telegram.org" not in caplog.text
    _FakeBot.error = None


@pytest.mark.asyncio
async def test_send_message_rejects_oversized_text(monkeypatch):
    _FakeBot.sent = []
    _FakeBot.error = None
    monkeypatch.setattr("services.bot_service.Bot", _FakeBot)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)

    delivered = await BotService.send_message(777, "x" * (BotService.MAX_MESSAGE_LENGTH + 1))

    assert delivered is False
    assert _FakeBot.sent == []


@pytest.mark.asyncio
async def test_installer_notification_escapes_untrusted_fields(monkeypatch):
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(BotService, "send_message", send_mock)

    delivered = await BotService.notify_installer_new_order(
        installer_tg_id=777,
        order_id=55,
        address="Минск <центр> & офис",
        date_str="12.07.2026 <утро>",
        role="Монтажник <главный>",
    )

    assert delivered is True
    sent_text = send_mock.await_args.args[1]
    assert "Минск &lt;центр&gt; &amp; офис" in sent_text
    assert "12.07.2026 &lt;утро&gt;" in sent_text
    assert "Монтажник &lt;главный&gt;" in sent_text
    assert "<центр>" not in sent_text


@pytest.mark.asyncio
async def test_send_rich_message_calls_telegram_bot_api(monkeypatch):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse({"ok": True, "result": {"message_id": 1}})
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
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
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
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
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)
    fallback = AsyncMock(return_value=True)
    monkeypatch.setattr(BotService, "send_message", fallback)

    delivered = await BotService.send_rich_message(777, "<h3>Заказ</h3>", fallback_text="fallback")

    assert delivered is True
    fallback.assert_awaited_once_with(777, "fallback", reply_markup=None)


@pytest.mark.asyncio
async def test_send_rich_message_returns_false_when_fallback_fails(monkeypatch):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse({"ok": False}, status_code=400)
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:test", raising=False)
    fallback = AsyncMock(return_value=False)
    monkeypatch.setattr(BotService, "send_message", fallback)

    delivered = await BotService.send_rich_message(777, "<h3>Заказ</h3>", fallback_text="fallback")

    assert delivered is False
    fallback.assert_awaited_once_with(777, "fallback", reply_markup=None)


@pytest.mark.asyncio
async def test_send_rich_message_does_not_log_token_or_url(monkeypatch, caplog):
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.response = _FakeResponse(
        raise_error=RuntimeError("https://api.telegram.org/bot123:secret-token/sendRichMessage")
    )
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "123:secret-token", raising=False)
    fallback = AsyncMock(return_value=False)
    monkeypatch.setattr(BotService, "send_message", fallback)

    with caplog.at_level("WARNING"):
        delivered = await BotService.send_rich_message(
            777,
            "<h3>Заказ</h3>",
            fallback_text="fallback",
        )

    assert delivered is False
    assert "123:secret-token" not in caplog.text
    assert "api.telegram.org" not in caplog.text


@pytest.mark.asyncio
async def test_send_rich_message_skips_without_bot_token(monkeypatch):
    _FakeAsyncClient.requests = []
    monkeypatch.setattr("services.bot_service.ClientSession", _FakeAsyncClient)
    monkeypatch.setattr("services.bot_service.settings.BOT_TOKEN", "", raising=False)
    fallback = AsyncMock()
    monkeypatch.setattr(BotService, "send_message", fallback)

    delivered = await BotService.send_rich_message(777, "<h3>Заказ</h3>", fallback_text="fallback")

    assert delivered is False
    assert _FakeAsyncClient.requests == []
    fallback.assert_not_awaited()
