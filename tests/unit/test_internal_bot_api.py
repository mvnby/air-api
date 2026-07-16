from httpx import ASGITransport, AsyncClient

from core.config import settings
from core.database import get_session
from main import app
from services.bot_access_service import BotAccessContext, BotAccessService


async def _request(path: str, *, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_internal_bot_api_fails_closed_when_token_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "")

    response = await _request("/api/internal/bot/v1/health", token="anything")

    assert response.status_code == 503
    assert response.json() == {"detail": "Bot API token is not configured"}


async def test_internal_bot_api_rejects_missing_and_invalid_tokens(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    missing = await _request("/api/internal/bot/v1/health")
    invalid = await _request("/api/internal/bot/v1/health", token="wrong-token")

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


async def test_internal_bot_api_rejects_request_before_opening_db_session(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    session_opened = False

    async def guarded_session():
        nonlocal session_opened
        session_opened = True
        yield object()

    app.dependency_overrides[get_session] = guarded_session
    try:
        response = await _request("/api/internal/bot/v1/staff/context/123", token="wrong-token")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401
    assert session_opened is False


async def test_internal_bot_api_health_uses_dedicated_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    response = await _request("/api/internal/bot/v1/health", token="expected-token")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}


def test_internal_bot_api_openapi_contract_is_versioned_and_secured():
    schema = app.openapi()

    health = schema["paths"]["/api/internal/bot/v1/health"]["get"]
    staff_context = schema["paths"]["/api/internal/bot/v1/staff/context/{telegram_id}"]["get"]

    assert health["operationId"] == "get_internal_bot_api_health_v1"
    assert staff_context["operationId"] == "get_internal_bot_staff_context_v1"
    assert health["security"] == [{"BotServiceBearer": []}]
    assert staff_context["security"] == [{"BotServiceBearer": []}]
    assert schema["components"]["securitySchemes"]["BotServiceBearer"] == {
        "type": "http",
        "description": "Dedicated bearer token used only by the MVN Telegram bot service.",
        "scheme": "bearer",
    }


async def test_internal_bot_staff_context_maps_backend_permissions(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_get_context(_session, telegram_id):
        assert telegram_id == 123456
        return BotAccessContext(
            telegram_id=telegram_id,
            is_staff=True,
            display_name="Монтажник",
            primary_role="installer",
            roles=["installer", "repair"],
            legacy_installer_id=42,
        )

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotAccessService, "get_context", fake_get_context)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/staff/context/123456",
            token="expected-token",
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 123456,
        "is_staff": True,
        "display_name": "Монтажник",
        "primary_role": "installer",
        "roles": ["installer", "repair"],
        "legacy_installer_id": 42,
        "is_manager": False,
        "is_executor": True,
    }
