import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.security import get_current_username
from routers.manager_google_auth import router as manager_google_auth_router


@pytest.fixture()
async def google_auth_client():
    app = FastAPI()
    app.include_router(manager_google_auth_router)
    app.dependency_overrides[get_current_username] = lambda: "admin"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_google_auth_status_endpoint(google_auth_client, monkeypatch):
    class _Svc:
        def get_token_status(self):
            return {
                "exists": True,
                "valid": True,
                "expired": False,
                "expiry": "2026-04-20 22:00:00",
                "scopes": ["drive"],
            }

    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: _Svc())
    response = await google_auth_client.get("/api/manager/google-auth/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["exists"] is True


@pytest.mark.asyncio
async def test_google_auth_url_endpoint(google_auth_client, monkeypatch):
    class _Svc:
        def get_auth_url(self):
            return "https://accounts.google.com/o/oauth2/auth?x=1"

    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: _Svc())
    response = await google_auth_client.get("/api/manager/google-auth/url")
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://accounts.google.com/")


@pytest.mark.asyncio
async def test_google_auth_exchange_endpoint(google_auth_client, monkeypatch):
    called = {"code": None}

    class _Svc:
        def finish_auth(self, code: str):
            called["code"] = code

    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: _Svc())
    response = await google_auth_client.post(
        "/api/manager/google-auth/exchange",
        json={"code": "test-code-123"},
    )
    assert response.status_code == 200
    assert called["code"] == "test-code-123"


@pytest.mark.asyncio
async def test_google_auth_exchange_requires_code(google_auth_client, monkeypatch):
    class _Svc:
        def finish_auth(self, code: str):
            raise AssertionError("finish_auth should not be called")

    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: _Svc())
    response = await google_auth_client.post(
        "/api/manager/google-auth/exchange",
        json={"code": "   "},
    )
    assert response.status_code == 400
