from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from core.config import settings
from core.database import get_session
from main import app
from services.bot_voice_quick_order_service import (
    BotVoiceQuickOrderResult,
    BotVoiceQuickOrderService,
)


async def test_voice_quick_order_endpoint_returns_transcript_and_draft(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    parse = AsyncMock(
        return_value=BotVoiceQuickOrderResult(
            transcript="Монтаж завтра в 10",
            draft={
                "name": None,
                "phone": None,
                "address": None,
                "service_type": "install_only",
                "service_label": "Монтаж",
                "target_date": None,
                "request_text": "Монтаж завтра в 10",
                "parser": "fallback",
                "address_check": None,
            },
        )
    )
    monkeypatch.setattr(BotVoiceQuickOrderService, "parse_for_manager", parse)

    async def fake_session():
        yield object()

    app.dependency_overrides[get_session] = fake_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/internal/bot/v1/quick-orders/parse-voice",
                headers={"Authorization": "Bearer expected-token"},
                data={
                    "telegram_id": "123",
                    "telegram_chat_id": "-456",
                    "telegram_message_id": "789",
                    "duration_seconds": "12",
                },
                files={"file": ("voice.ogg", b"OggSvoice", "audio/ogg")},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json()["transcript"] == "Монтаж завтра в 10"
    assert response.json()["draft"]["service_type"] == "install_only"
    parse.assert_awaited_once()
    assert parse.await_args.kwargs["telegram_chat_id"] == -456
    assert parse.await_args.kwargs["content"] == b"OggSvoice"


def test_voice_quick_order_openapi_contract_is_private_and_multipart():
    operation = app.openapi()["paths"][
        "/api/internal/bot/v1/quick-orders/parse-voice"
    ]["post"]

    assert operation["operationId"] == "parse_internal_bot_voice_quick_order_v1"
    assert operation["security"] == [{"BotServiceBearer": []}]
    assert "multipart/form-data" in operation["requestBody"]["content"]
