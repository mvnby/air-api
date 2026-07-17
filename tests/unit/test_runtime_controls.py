import importlib
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.runtime_controls import resolve_single_active_control


class FakeRuntimeLock:
    acquired = True
    reason = "test lock"

    async def release(self):
        return None


def _set_required_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:test")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")


def _production_private_storage_values() -> dict[str, str]:
    return {
        "SERVICE_ATTACHMENT_STORAGE_PROVIDER": "r2",
        "SERVICE_ATTACHMENT_S3_BUCKET": "test-private-service-attachments",
        "SERVICE_ATTACHMENT_S3_ENDPOINT_URL": "https://account.r2.invalid",
        "SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID": "test-access-key",
        "SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY": "test-secret-key",
    }


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
        API_READY_ENABLED="",
        DB_BOOTSTRAP_ENABLED="",
        _env_file=None,
    )

    assert settings.SCHEDULER_ENABLED is None
    assert settings.BOT_ENABLED is None
    assert settings.API_READY_ENABLED is None
    assert settings.DB_BOOTSTRAP_ENABLED is None
    assert settings.scheduler_control_decision.enabled is True
    assert settings.bot_control_decision.enabled is True
    assert settings.api_ready_control_decision.enabled is True
    assert settings.db_bootstrap_control_decision.enabled is True


@pytest.mark.parametrize(("value", "expected"), [("database", "database"), (" API ", "api")])
def test_bot_access_backend_is_explicit_and_normalized(monkeypatch, value, expected):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    settings = config.Settings(
        BOT_TOKEN="123:test",
        SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="admin",
        BOT_ACCESS_BACKEND=value,
        BOT_API_TOKEN="service-token" if expected == "api" else "",
        _env_file=None,
    )

    assert settings.BOT_ACCESS_BACKEND == expected


def test_bot_access_backend_rejects_implicit_fallback(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    with pytest.raises(ValueError, match="BOT_ACCESS_BACKEND"):
        config.Settings(
            BOT_TOKEN="123:test",
            SECRET_KEY="test-secret",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="admin",
            BOT_ACCESS_BACKEND="auto",
            _env_file=None,
        )


def test_bot_api_backend_requires_service_token(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    with pytest.raises(ValueError, match="BOT_API_TOKEN is required"):
        config.Settings(
            BOT_TOKEN="123:test",
            SECRET_KEY="test-secret",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="admin",
            BOT_ACCESS_BACKEND="api",
            BOT_API_TOKEN="",
            _env_file=None,
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.mvn.by/api/internal/bot/v1",
        "https://app/api/internal/bot/v1",
        "https://app-blue/api/internal/bot/v1",
    ],
)
def test_production_bot_api_backend_requires_stable_https_origin(monkeypatch, base_url):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    with pytest.raises(ValueError, match="production Bot API access"):
        config.Settings(
            BOT_TOKEN="123:test",
            SECRET_KEY="test-secret",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="admin",
            ENVIRONMENT="production",
            BOT_ACCESS_BACKEND="api",
            BOT_API_TOKEN="service-token",
            BOT_API_BASE_URL=base_url,
            _env_file=None,
            **_production_private_storage_values(),
        )


def test_production_bot_api_backend_accepts_stable_https_origin(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")

    settings = config.Settings(
        BOT_TOKEN="123:test",
        SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="admin",
        ENVIRONMENT="production",
        BOT_ACCESS_BACKEND="api",
        BOT_API_TOKEN="service-token",
        BOT_API_BASE_URL="https://api.mvn.by/api/internal/bot/v1",
        _env_file=None,
        **_production_private_storage_values(),
    )

    assert settings.BOT_API_BASE_URL == "https://api.mvn.by/api/internal/bot/v1"


@pytest.mark.asyncio
async def test_database_bootstrap_skips_for_standby(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "DB_BOOTSTRAP_ENABLED", None, raising=False)
    init_db = AsyncMock()
    seed_defaults = AsyncMock()
    monkeypatch.setattr(app_lifespan, "init_db", init_db)
    monkeypatch.setattr(app_lifespan, "_seed_installation_defaults", seed_defaults)

    assert await app_lifespan._bootstrap_database() is False
    init_db.assert_not_awaited()
    seed_defaults.assert_not_awaited()


@pytest.mark.asyncio
async def test_database_bootstrap_runs_for_primary(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "DB_BOOTSTRAP_ENABLED", None, raising=False)
    init_db = AsyncMock()
    seed_defaults = AsyncMock()
    monkeypatch.setattr(app_lifespan, "init_db", init_db)
    monkeypatch.setattr(app_lifespan, "_seed_installation_defaults", seed_defaults)

    assert await app_lifespan._bootstrap_database() is True
    init_db.assert_awaited_once_with()
    seed_defaults.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_database_bootstrap_explicit_switch_overrides_standby(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "DB_BOOTSTRAP_ENABLED", True, raising=False)
    init_db = AsyncMock()
    seed_defaults = AsyncMock()
    monkeypatch.setattr(app_lifespan, "init_db", init_db)
    monkeypatch.setattr(app_lifespan, "_seed_installation_defaults", seed_defaults)

    assert await app_lifespan._bootstrap_database() is True
    init_db.assert_awaited_once_with()
    seed_defaults.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_catalog_import_resume_runs_inside_scheduler_lock(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    resume_pending_jobs = AsyncMock(return_value=True)
    monkeypatch.setitem(
        sys.modules,
        "services.catalog_import_runtime_service",
        SimpleNamespace(
            catalog_import_runtime_service=SimpleNamespace(
                resume_pending_jobs=resume_pending_jobs,
            ),
        ),
    )

    assert await app_lifespan._resume_catalog_import_jobs() is True
    resume_pending_jobs.assert_awaited_once_with()


def test_start_scheduler_loop_skips_for_standby(monkeypatch):
    _set_required_env(monkeypatch)
    app_lifespan = importlib.import_module("core.app_lifespan")

    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "SCHEDULER_ENABLED", None, raising=False)
    create_task = Mock()
    monkeypatch.setattr(app_lifespan.asyncio, "create_task", create_task)

    assert app_lifespan._start_scheduler_loop(SimpleNamespace(state=SimpleNamespace())) is False
    create_task.assert_not_called()


def test_bot_main_registers_staff_commands(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    monkeypatch.setattr(config.settings, "BOT_TOKEN", "123:test", raising=False)
    bot_main = importlib.import_module("bot_app.main")

    commands = {command.command: command.description for command in bot_main.STAFF_BOT_COMMANDS}

    assert commands["menu"] == "Показать рабочее меню"
    assert commands["help"] == "Показать рабочее меню и подсказки"
    assert commands["quick_order"] == "Быстрый заказ из текста звонка"
    assert commands["selection"] == "Подбор кондиционеров: 7х2, 7, 12"
    assert commands["search"] == "Поиск товара: Midea 12"
    assert commands["tasks"] == "Мои задачи и отчеты"


def test_bot_config_allows_empty_token_when_disabled(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    bot_config = importlib.import_module("bot_app.config")

    monkeypatch.setattr(bot_config.settings, "BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(bot_config.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(bot_config.settings, "BOT_ENABLED", None, raising=False)

    assert bot_config._resolve_bot_token() == "0:disabled-bot-token"


def test_bot_config_requires_token_when_enabled(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    bot_config = importlib.import_module("bot_app.config")

    monkeypatch.setattr(bot_config.settings, "BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(bot_config.settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(bot_config.settings, "BOT_ENABLED", True, raising=False)

    with pytest.raises(RuntimeError, match="BOT_TOKEN is required"):
        bot_config._resolve_bot_token()


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
    verify_access = AsyncMock()
    monkeypatch.setattr(bot_main.bot, "delete_webhook", delete_webhook)
    monkeypatch.setattr(bot_main.dp, "start_polling", start_polling)
    monkeypatch.setattr(bot_main, "verify_bot_access_startup", verify_access)

    await bot_main.main(wait_when_disabled=False)

    verify_access.assert_not_awaited()
    delete_webhook.assert_not_awaited()
    start_polling.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_main_preserves_pending_updates_by_default(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    monkeypatch.setattr(config.settings, "BOT_TOKEN", "123:test", raising=False)
    bot_main = importlib.import_module("bot_app.main")

    monkeypatch.setattr(bot_main.settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(bot_main.settings, "BOT_ENABLED", True, raising=False)
    monkeypatch.setattr(bot_main.settings, "BOT_DROP_PENDING_UPDATES", False, raising=False)
    monkeypatch.setattr(bot_main.dp, "include_router", Mock())
    setup_commands = AsyncMock()
    delete_webhook = AsyncMock()
    start_polling = AsyncMock()
    verify_access = AsyncMock()
    close_access = AsyncMock()
    lease = SimpleNamespace(
        lost_event=asyncio.Event(),
        try_acquire=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    monkeypatch.setattr(bot_main, "_setup_bot_commands", setup_commands)
    monkeypatch.setattr(bot_main.bot, "delete_webhook", delete_webhook)
    monkeypatch.setattr(bot_main.dp, "start_polling", start_polling)
    monkeypatch.setattr(bot_main, "verify_bot_access_startup", verify_access)
    monkeypatch.setattr(bot_main, "close_bot_access_provider", close_access)
    monkeypatch.setattr(bot_main, "close_bot_api_gateway", AsyncMock())
    monkeypatch.setattr(bot_main, "BotRuntimeLease", Mock(return_value=lease))

    await bot_main.main(wait_when_disabled=False)

    verify_access.assert_awaited_once_with()
    setup_commands.assert_awaited_once()
    delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    start_polling.assert_awaited_once_with(bot_main.bot)
    close_access.assert_awaited_once_with()
    lease.try_acquire.assert_awaited_once_with()
    lease.release.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_bot_main_does_not_poll_when_access_preflight_fails(monkeypatch):
    _set_required_env(monkeypatch)
    config = importlib.import_module("core.config")
    monkeypatch.setattr(config.settings, "BOT_TOKEN", "123:test", raising=False)
    bot_main = importlib.import_module("bot_app.main")

    monkeypatch.setattr(bot_main.settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(bot_main.settings, "BOT_ENABLED", True, raising=False)
    monkeypatch.setattr(bot_main.dp, "include_router", Mock())
    lease = SimpleNamespace(
        lost_event=asyncio.Event(),
        try_acquire=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    monkeypatch.setattr(bot_main, "BotRuntimeLease", Mock(return_value=lease))
    monkeypatch.setattr(
        bot_main,
        "verify_bot_access_startup",
        AsyncMock(side_effect=bot_main.BotAccessUnavailableError("offline")),
    )
    close_access = AsyncMock()
    start_polling = AsyncMock()
    monkeypatch.setattr(bot_main, "close_bot_access_provider", close_access)
    monkeypatch.setattr(bot_main, "close_bot_api_gateway", AsyncMock())
    monkeypatch.setattr(bot_main.dp, "start_polling", start_polling)

    with pytest.raises(bot_main.BotAccessUnavailableError, match="offline"):
        await bot_main.main(wait_when_disabled=False)

    start_polling.assert_not_awaited()
    close_access.assert_awaited_once_with()
    lease.try_acquire.assert_not_awaited()
    lease.release.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_bot_access_error_is_visible_to_callback(monkeypatch):
    _set_required_env(monkeypatch)
    bot_main = importlib.import_module("bot_app.main")
    callback = SimpleNamespace(answer=AsyncMock())
    event = SimpleNamespace(
        exception=bot_main.BotAccessUnavailableError("offline"),
        update=SimpleNamespace(callback_query=callback, message=None),
    )

    assert await bot_main.error_handler(event) is True

    callback.answer.assert_awaited_once_with(
        "Сервис авторизации временно недоступен. Попробуйте позже.",
        show_alert=True,
    )


@pytest.mark.asyncio
async def test_bot_backend_api_error_is_visible_to_message(monkeypatch):
    _set_required_env(monkeypatch)
    bot_main = importlib.import_module("bot_app.main")
    from bot_app.api_gateway import BotApiUnavailableError

    message = SimpleNamespace(answer=AsyncMock())
    event = SimpleNamespace(
        exception=BotApiUnavailableError("offline"),
        update=SimpleNamespace(callback_query=None, message=message),
    )

    assert await bot_main.error_handler(event) is True

    message.answer.assert_awaited_once_with(
        "Рабочий сервис временно недоступен. Попробуйте позже."
    )


@pytest.mark.asyncio
async def test_bot_backend_authorization_error_is_not_reported_as_outage(monkeypatch):
    _set_required_env(monkeypatch)
    bot_main = importlib.import_module("bot_app.main")
    from bot_app.api_gateway import BotApiAuthorizationError

    callback = SimpleNamespace(answer=AsyncMock())
    event = SimpleNamespace(
        exception=BotApiAuthorizationError("denied"),
        update=SimpleNamespace(callback_query=callback, message=None),
    )

    assert await bot_main.error_handler(event) is True

    callback.answer.assert_awaited_once_with(
        "Недостаточно прав для этого действия.",
        show_alert=True,
    )
