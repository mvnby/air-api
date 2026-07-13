from urllib.parse import parse_qs, urlencode, urlparse
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from core.config import settings
from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_owner_username,
    require_owner_access,
)
from routers.manager_google_auth import (
    GOOGLE_OAUTH_STATE_TTL_SECONDS,
    _oauth_owner_binding_is_active,
)
from routers.manager_google_auth import router as manager_google_auth_router


class _GoogleServiceStub:
    def __init__(self, *, finish_error: Exception | None = None):
        self.auth_calls: list[dict[str, str]] = []
        self.finish_calls: list[dict[str, str]] = []
        self.finish_error = finish_error

    def get_token_status(self):
        return {
            "exists": True,
            "valid": True,
            "expired": False,
            "expiry": "2026-04-20 22:00:00",
            "scopes": ["drive"],
            "persistence_ok": True,
            "persistence_error_code": None,
        }

    def get_auth_url(self, redirect_uri=None, *, state: str):
        self.auth_calls.append({"redirect_uri": redirect_uri, "state": state})
        return f"https://accounts.google.com/o/oauth2/auth?{urlencode({'state': state})}"

    def finish_auth(self, code: str, redirect_uri=None):
        self.finish_calls.append({"code": code, "redirect_uri": redirect_uri})
        if self.finish_error:
            raise self.finish_error


@pytest.fixture()
async def google_auth_client(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="google-oauth-test-session-secret",
        same_site="lax",
        https_only=False,
    )
    app.include_router(manager_google_auth_router)
    app.dependency_overrides[get_current_owner_username] = lambda: "admin"
    app.dependency_overrides[require_owner_access] = lambda: AuthenticatedUser(
        username=settings.ADMIN_USERNAME,
        auth_source="legacy",
        role="owner",
    )

    async def _override_session():
        yield object()

    app.dependency_overrides[get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _state_from_response(response) -> str:
    auth_url = response.json()["url"]
    return parse_qs(urlparse(auth_url).query)["state"][0]


@pytest.mark.asyncio
async def test_google_auth_status_endpoint(google_auth_client, monkeypatch):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)

    response = await google_auth_client.get("/api/manager/google-auth/status")

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["exists"] is True
    assert response.json()["persistence_ok"] is True


@pytest.mark.asyncio
async def test_google_auth_url_stores_session_and_forwards_state(google_auth_client, monkeypatch):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)

    response = await google_auth_client.get("/api/manager/google-auth/url")

    assert response.status_code == 200
    state = _state_from_response(response)
    assert len(state) >= 32
    assert service.auth_calls == [
        {
            "redirect_uri": "http://test/api/manager/google-auth/callback",
            "state": state,
        }
    ]
    assert google_auth_client.cookies.get("session")


@pytest.mark.asyncio
async def test_google_auth_url_uses_configured_redirect_uri_in_production(
    google_auth_client,
    monkeypatch,
):
    class _ProductionSettings:
        is_production = True

    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.settings", _ProductionSettings())
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "https://api.mvn.by/api/manager/google-auth/callback",
    )
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)

    response = await google_auth_client.get("/api/manager/google-auth/url")

    assert response.status_code == 200
    assert service.auth_calls[0]["redirect_uri"] == "https://api.mvn.by/api/manager/google-auth/callback"


@pytest.mark.asyncio
async def test_google_auth_url_rejects_derived_redirect_in_production(
    google_auth_client,
    monkeypatch,
):
    class _ProductionSettings:
        is_production = True

    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.settings", _ProductionSettings())
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)

    response = await google_auth_client.get("/api/manager/google-auth/url")

    assert response.status_code == 503
    assert response.json()["detail"] == "Google OAuth redirect URI is not configured"
    assert service.auth_calls == []


@pytest.mark.asyncio
async def test_google_auth_callback_success_is_single_use(google_auth_client, monkeypatch):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    start_response = await google_auth_client.get("/api/manager/google-auth/url")
    state = _state_from_response(start_response)

    response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": state},
    )
    replay_response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": state},
    )

    assert response.status_code == 200
    assert replay_response.status_code == 400
    assert service.finish_calls == [
        {
            "code": "callback-code",
            "redirect_uri": "http://test/api/manager/google-auth/callback",
        }
    ]


@pytest.mark.asyncio
async def test_google_auth_callback_rejects_missing_state_without_provider_call(
    google_auth_client,
    monkeypatch,
):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    await google_auth_client.get("/api/manager/google-auth/url")

    response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code"},
    )

    assert response.status_code == 400
    assert service.finish_calls == []


@pytest.mark.asyncio
async def test_google_auth_callback_rejects_wrong_state_without_consuming_valid_state(
    google_auth_client,
    monkeypatch,
):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    start_response = await google_auth_client.get("/api/manager/google-auth/url")
    state = _state_from_response(start_response)

    wrong_response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": "неверный-state"},
    )
    valid_response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": state},
    )

    assert wrong_response.status_code == 400
    assert valid_response.status_code == 200
    assert len(service.finish_calls) == 1


@pytest.mark.asyncio
async def test_google_auth_callback_rejects_expired_state(google_auth_client, monkeypatch):
    clock = {"now": 1_000.0}
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth._oauth_now", lambda: clock["now"])
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    start_response = await google_auth_client.get("/api/manager/google-auth/url")
    state = _state_from_response(start_response)
    clock["now"] += GOOGLE_OAUTH_STATE_TTL_SECONDS + 1

    response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": state},
    )

    assert response.status_code == 400
    assert service.finish_calls == []


@pytest.mark.asyncio
async def test_google_auth_callback_redacts_provider_error(google_auth_client, monkeypatch):
    secret_error = "provider failed with client_secret=do-not-expose"
    service = _GoogleServiceStub(finish_error=RuntimeError(secret_error))
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    start_response = await google_auth_client.get("/api/manager/google-auth/url")
    state = _state_from_response(start_response)

    response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"code": "callback-code", "state": state},
    )

    assert response.status_code == 502
    assert secret_error not in response.text
    assert "Google authentication service is unavailable" in response.text


@pytest.mark.asyncio
async def test_google_auth_callback_redacts_provider_query_error(google_auth_client, monkeypatch):
    service = _GoogleServiceStub()
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: service)
    start_response = await google_auth_client.get("/api/manager/google-auth/url")
    state = _state_from_response(start_response)

    response = await google_auth_client.get(
        "/api/manager/google-auth/callback",
        params={"error": "secret-provider-error", "state": state},
    )

    assert response.status_code == 400
    assert "secret-provider-error" not in response.text
    assert service.finish_calls == []


@pytest.mark.asyncio
async def test_google_auth_exchange_endpoint_is_closed(google_auth_client):
    response = await google_auth_client.post(
        "/api/manager/google-auth/exchange",
        json={"code": "manual-code"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_google_auth_owner_binding_rejects_demoted_staff(monkeypatch):
    async def fake_get_by_id(_session, staff_user_id):
        assert staff_user_id == 42
        return SimpleNamespace(status="active", primary_role="manager", roles=["manager"])

    monkeypatch.setattr(
        "routers.manager_google_auth.StaffUserService.get_by_id",
        fake_get_by_id,
    )

    assert await _oauth_owner_binding_is_active(
        object(),
        {
            "auth_source": "staff",
            "staff_user_id": 42,
            "username": "manager",
        },
    ) is False
