from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramConflictError,
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.methods import SendMessage

from services.communications.providers.base import ProviderDeliveryDisposition
from services.communications.providers.telegram import TelegramDeliveryProvider


class FakeBot:
    outcome = None
    calls = []

    def __init__(self, *, token: str):
        self.token = token
        self.session = SimpleNamespace(close=self._close)

    async def _close(self):
        return None

    async def send_message(self, **kwargs):
        type(self).calls.append(kwargs)
        if isinstance(type(self).outcome, BaseException):
            raise type(self).outcome
        return type(self).outcome


@pytest.fixture(autouse=True)
def fake_bot(monkeypatch):
    FakeBot.outcome = SimpleNamespace(message_id=42)
    FakeBot.calls = []
    monkeypatch.setattr(
        "services.communications.providers.telegram.Bot",
        FakeBot,
    )


@pytest.mark.asyncio
async def test_telegram_provider_sends_html_and_returns_provider_message_id():
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    result = await provider.send(
        destination="-100123",
        text="<b>Новая заявка</b>",
        delivery_id="1" * 32,
    )

    assert result.disposition == ProviderDeliveryDisposition.SENT
    assert result.provider_message_id == "42"
    assert FakeBot.calls == [
        {
            "chat_id": -100123,
            "text": "<b>Новая заявка</b>",
            "parse_mode": "HTML",
        }
    ]


@pytest.mark.asyncio
async def test_telegram_provider_preserves_retry_after():
    method = SendMessage(chat_id=101, text="test")
    FakeBot.outcome = TelegramRetryAfter(
        method=method,
        message="Flood control",
        retry_after=9876,
    )
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    result = await provider.send(
        destination="101",
        text="test",
        delivery_id="2" * 32,
    )

    assert result.disposition == ProviderDeliveryDisposition.TRANSIENT_FAILURE
    assert result.error_code == "telegram_retry_after"
    assert result.retry_after_seconds == 9876


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception_type", "expected_disposition", "expected_code"),
    [
        (
            TelegramForbiddenError,
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_recipient_unavailable",
        ),
        (
            TelegramUnauthorizedError,
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_provider_auth_or_conflict",
        ),
    ],
)
async def test_telegram_provider_classifies_recipient_and_provider_failures(
    exception_type,
    expected_disposition,
    expected_code,
):
    method = SendMessage(chat_id=101, text="test")
    FakeBot.outcome = exception_type(method=method, message="provider detail")
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    result = await provider.send(
        destination="101",
        text="test",
        delivery_id="3" * 32,
    )

    assert result.disposition == expected_disposition
    assert result.error_code == expected_code
    assert "provider detail" not in (result.error_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception_factory", "expected_disposition", "expected_code"),
    [
        (
            lambda method: TelegramEntityTooLarge(method=method, message="too large"),
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_entity_too_large",
        ),
        (
            lambda method: TelegramNotFound(method=method, message="not found"),
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_recipient_unavailable",
        ),
        (
            lambda method: TelegramMigrateToChat(
                method=method,
                message="migrated",
                migrate_to_chat_id=-100987,
            ),
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_chat_migrated",
        ),
        (
            lambda method: TelegramBadRequest(method=method, message="bad request"),
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_bad_request",
        ),
        (
            lambda method: TelegramConflictError(method=method, message="conflict"),
            ProviderDeliveryDisposition.PERMANENT_FAILURE,
            "telegram_provider_auth_or_conflict",
        ),
        (
            lambda method: TelegramNetworkError(method=method, message="network"),
            ProviderDeliveryDisposition.AMBIGUOUS_FAILURE,
            "telegram_network_error",
        ),
        (
            lambda method: TelegramServerError(method=method, message="server"),
            ProviderDeliveryDisposition.AMBIGUOUS_FAILURE,
            "telegram_network_error",
        ),
        (
            lambda _method: TimeoutError("timeout"),
            ProviderDeliveryDisposition.AMBIGUOUS_FAILURE,
            "telegram_network_error",
        ),
        (
            lambda method: TelegramAPIError(method=method, message="generic API"),
            ProviderDeliveryDisposition.AMBIGUOUS_FAILURE,
            "telegram_api_error",
        ),
    ],
)
async def test_telegram_provider_classifies_all_provider_error_families(
    exception_factory,
    expected_disposition,
    expected_code,
):
    method = SendMessage(chat_id=101, text="test")
    FakeBot.outcome = exception_factory(method)
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    result = await provider.send(
        destination="101",
        text="test",
        delivery_id="7" * 32,
    )

    assert result.disposition == expected_disposition
    assert result.error_code == expected_code


@pytest.mark.asyncio
async def test_telegram_provider_propagates_explicit_cancellation():
    FakeBot.outcome = asyncio.CancelledError()
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    with pytest.raises(asyncio.CancelledError):
        await provider.send(
            destination="101",
            text="test",
            delivery_id="8" * 32,
        )


@pytest.mark.asyncio
async def test_telegram_provider_rejects_invalid_payload_without_network():
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    invalid_destination = await provider.send(
        destination="not-a-chat",
        text="test",
        delivery_id="4" * 32,
    )
    oversized = await provider.send(
        destination="101",
        text="x" * 4097,
        delivery_id="5" * 32,
    )

    assert invalid_destination.disposition == ProviderDeliveryDisposition.PERMANENT_FAILURE
    assert invalid_destination.error_code == "telegram_destination_invalid"
    assert oversized.disposition == ProviderDeliveryDisposition.PERMANENT_FAILURE
    assert oversized.error_code == "telegram_text_invalid"
    assert FakeBot.calls == []


@pytest.mark.asyncio
async def test_telegram_provider_does_not_expose_unknown_exception_message(caplog):
    FakeBot.outcome = RuntimeError(
        "request failed at https://api.telegram.org/bot123456:secret-token/sendMessage"
    )
    provider = TelegramDeliveryProvider(token="123456:secret-token")

    result = await provider.send(
        destination="101",
        text="test",
        delivery_id="6" * 32,
    )

    assert result.disposition == ProviderDeliveryDisposition.AMBIGUOUS_FAILURE
    assert (
        result.error_message
        == "Telegram provider outcome requires manual reconciliation"
    )
    assert "secret-token" not in caplog.text
