import pytest

from bot_app.settings import BotSettings


def test_production_bot_settings_require_stable_https_api(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BOT_API_BASE_URL", "http://app:8000/api/internal/bot/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        BotSettings()


def test_bot_runtime_renewal_must_fit_inside_lease(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("BOT_RUNTIME_LEASE_SECONDS", "30")
    monkeypatch.setenv("BOT_RUNTIME_RENEW_SECONDS", "30")
    with pytest.raises(ValueError, match="shorter than the lease"):
        BotSettings()


def test_bot_settings_accept_stable_production_origin(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BOT_API_BASE_URL", "https://api.mvn.by/api/internal/bot/v1")
    configured = BotSettings()
    assert configured.BOT_API_BASE_URL.startswith("https://api.mvn.by/")
