import importlib
from unittest.mock import AsyncMock, Mock

import pytest

from core.runtime_controls import resolve_single_active_control


def _set_required_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:test")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")


def test_standby_role_disables_scheduler_by_default():
    decision = resolve_single_active_control(
        app_role="standby",
        explicit_enabled=None,
        env_var_name="SCHEDULER_ENABLED",
        process_label="scheduler loops",
    )

    assert decision.enabled is False
    assert "APP_ROLE=standby" in decision.reason


def test_primary_role_enables_scheduler_by_default():
    decision = resolve_single_active_control(
        app_role="primary",
        explicit_enabled=None,
        env_var_name="SCHEDULER_ENABLED",
        process_label="scheduler loops",
    )

    assert decision.enabled is True
    assert "APP_ROLE=primary" in decision.reason


def test_explicit_switch_overrides_app_role():
    decision = resolve_single_active_control(
        app_role="standby",
        explicit_enabled=True,
        env_var_name="SCHEDULER_ENABLED",
        process_label="scheduler loops",
    )

    assert decision.enabled is True
    assert "SCHEDULER_ENABLED=true" in decision.reason


def test_unknown_app_role_fails_closed():
    decision = resolve_single_active_control(
        app_role="api",
        explicit_enabled=None,
        env_var_name="BOT_ENABLED",
        process_label="Telegram bot polling",
    )

    assert decision.enabled is False
    assert "not an active role" in decision.reason


def test_empty_runtime_switch_env_values_are_unset(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    settings = config.Settings(
        BOT_TOKEN="123:test",
        SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="admin",
        SCHEDULER_ENABLED="",
        BOT_ENABLED="",
        _env_file=None,
    )

    assert settings.SCHEDULER_ENABLED is None
    assert settings.BOT_ENABLED is None
    assert settings.scheduler_control_decision.enabled is True
    assert settings.bot_control_decision.enabled is True


def test_start_scheduler_loop_skips_for_standby(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "SCHEDULER_ENABLED", None, raising=False)
    create_task = Mock()
    monkeypatch.setattr(app_lifespan.asyncio, "create_task", create_task)

    assert app_lifespan._start_scheduler_loop() is False
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_bot_main_disabled_does_not_poll(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    monkeypatch.setattr(config.settings, "BOT_TOKEN", "123:test", raising=False)
    bot_main = importlib.import_module("bot_app.main")

    monkeypatch.setattr(bot_main.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(bot_main.settings, "BOT_ENABLED", None, raising=False)
    delete_webhook = AsyncMock()
    start_polling = AsyncMock()
    monkeypatch.setattr(bot_main.bot, "delete_webhook", delete_webhook)
    monkeypatch.setattr(bot_main.dp, "start_polling", start_polling)

    await bot_main.main(wait_when_disabled=False)

    delete_webhook.assert_not_awaited()
    start_polling.assert_not_awaited()
