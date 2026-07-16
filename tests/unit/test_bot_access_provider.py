from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import BotApiHealthResponse, BotStaffContextResponse
from bot_app import access_runtime
from bot_app.access import BotAccessContext, BotAccessUnavailableError
from bot_app.access_api import ApiBotAccessProvider
from bot_app.api_gateway import BotApiUnavailableError


async def test_api_access_provider_maps_staff_context():
    gateway = SimpleNamespace(
        get_staff_context=AsyncMock(
            return_value=BotStaffContextResponse(
                telegram_id=123,
                is_staff=True,
                display_name="Менеджер",
                primary_role="manager",
                roles=["manager"],
                is_manager=True,
                is_executor=False,
            )
        ),
        health=AsyncMock(return_value=BotApiHealthResponse()),
        aclose=AsyncMock(),
    )
    provider = ApiBotAccessProvider(gateway)

    context = await provider.get_context("123")

    assert context == BotAccessContext(
        telegram_id=123,
        is_staff=True,
        display_name="Менеджер",
        primary_role="manager",
        roles=["manager"],
        is_manager=True,
        is_executor=False,
    )
    gateway.get_staff_context.assert_awaited_once_with(123)


@pytest.mark.parametrize("telegram_id", [None, "", "invalid", 0, -1])
async def test_api_access_provider_rejects_invalid_user_without_http_call(telegram_id):
    gateway = SimpleNamespace(
        get_staff_context=AsyncMock(),
        health=AsyncMock(),
        aclose=AsyncMock(),
    )
    provider = ApiBotAccessProvider(gateway)

    context = await provider.get_context(telegram_id)

    assert context == BotAccessContext(telegram_id=0)
    gateway.get_staff_context.assert_not_awaited()


async def test_api_access_provider_fails_closed_when_api_is_unavailable():
    gateway = SimpleNamespace(
        get_staff_context=AsyncMock(side_effect=BotApiUnavailableError("offline")),
        health=AsyncMock(),
        aclose=AsyncMock(),
    )
    provider = ApiBotAccessProvider(gateway)

    with pytest.raises(BotAccessUnavailableError, match="staff access is unavailable"):
        await provider.get_context(123)


async def test_access_runtime_checks_health_and_closes_provider(monkeypatch):
    provider = SimpleNamespace(
        health=AsyncMock(),
        get_context=AsyncMock(return_value=BotAccessContext(telegram_id=7, is_staff=True)),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(access_runtime, "_provider", provider)

    await access_runtime.verify_bot_access_startup()
    context = await access_runtime.get_bot_access_context(7)
    await access_runtime.close_bot_access_provider()

    assert context.is_staff is True
    provider.health.assert_awaited_once_with()
    provider.get_context.assert_awaited_once_with(7)
    provider.aclose.assert_awaited_once_with()
    assert access_runtime._provider is None


def test_api_access_backend_requires_service_token(monkeypatch):
    monkeypatch.setattr(access_runtime, "_provider", None)
    monkeypatch.setattr(access_runtime.settings, "BOT_ACCESS_BACKEND", "api")
    monkeypatch.setattr(access_runtime.settings, "BOT_API_TOKEN", "")

    with pytest.raises(ValueError, match="Bot API token is required"):
        access_runtime.get_bot_access_provider()


def test_access_runtime_never_implicitly_falls_back_to_database(monkeypatch):
    monkeypatch.setattr(access_runtime, "_provider", None)
    monkeypatch.setattr(access_runtime.settings, "BOT_ACCESS_BACKEND", "unexpected")

    with pytest.raises(RuntimeError, match="Unsupported bot access backend"):
        access_runtime.get_bot_access_provider()
