from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access, require_owner_access
from routers.manager_document_drive import router
from routers.manager_google_auth import router as manager_google_auth_router
from schemas_document_drive import DocumentDriveStatusResponse


class _Provider:
    def __init__(self) -> None:
        self.authorization_calls = []
        self.exchange_calls = []

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        self.authorization_calls.append((redirect_uri, state))
        return f"https://accounts.google.com/o/oauth2/auth?{urlencode({'state': state})}"

    def exchange_code(self, *, redirect_uri: str, code: str):
        self.exchange_calls.append((redirect_uri, code))
        return {"access_token": "temporary", "refresh_token": "secret"}


@pytest.fixture
async def document_drive_client(monkeypatch):
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="document-drive-session-secret",
        same_site="lax",
        https_only=False,
    )
    app.include_router(manager_google_auth_router)
    app.include_router(router)
    auth = AuthenticatedUser(
        username="tenant-owner",
        auth_source="staff_password",
        staff_user_id=5,
        role="owner",
        tenant_id=21,
        storefront_id=71,
        tenant_membership_id=31,
        auth_version=4,
    )
    app.dependency_overrides[require_manager_access] = lambda: auth
    app.dependency_overrides[require_owner_access] = lambda: auth

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    provider = _Provider()
    monkeypatch.setattr(
        "routers.manager_document_drive.get_document_drive_provider",
        lambda: provider,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, provider, auth


@pytest.mark.asyncio
async def test_status_is_tenant_scoped(document_drive_client, monkeypatch):
    client, _, auth = document_drive_client
    status = DocumentDriveStatusResponse(
        connected=True,
        account_label="owner@example.com",
        managed_folder_url="https://drive.google.com/drive/folders/folder-21",
    )
    read_status = AsyncMock(return_value=status)
    monkeypatch.setattr(
        "routers.manager_document_drive.DocumentDriveConnectionService.status",
        read_status,
    )

    response = await client.get("/api/manager/document-drive/status")

    assert response.status_code == 200
    assert response.json()["connected"] is True
    read_status.assert_awaited_once()
    assert read_status.await_args.kwargs["tenant_scope"] == auth.tenant_scope()


@pytest.mark.asyncio
async def test_authorization_url_preserves_tenant_binding(document_drive_client):
    client, provider, _ = document_drive_client

    response = await client.get("/api/manager/document-drive/authorization-url")

    assert response.status_code == 200
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    assert provider.authorization_calls == [
        ("http://test/api/manager/google-auth/callback", state)
    ]
    assert client.cookies.get("session")


@pytest.mark.asyncio
async def test_callback_persists_connection_for_bound_actor(
    document_drive_client,
    monkeypatch,
):
    client, provider, auth = document_drive_client
    start = await client.get("/api/manager/document-drive/authorization-url")
    state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    pending_scope = auth.tenant_scope()
    monkeypatch.setattr(
        "routers.manager_document_drive.pending_actor_scope",
        AsyncMock(return_value=pending_scope),
    )
    complete = AsyncMock(
        return_value=DocumentDriveStatusResponse(connected=True)
    )
    monkeypatch.setattr(
        "routers.manager_document_drive.DocumentDriveConnectionService.complete_authorization",
        complete,
    )

    response = await client.get(
        "/api/manager/google-auth/callback",
        params={"code": "one-time-code", "state": state},
    )
    replay = await client.get(
        "/api/manager/google-auth/callback",
        params={"code": "one-time-code", "state": state},
    )

    assert response.status_code == 200
    assert replay.status_code == 400
    assert response.text.count("window.close();") == 1
    assert response.text.index("window.close();") > response.text.index("if (window.opener)")
    assert provider.exchange_calls == [
        ("http://test/api/manager/google-auth/callback", "one-time-code")
    ]
    complete.assert_awaited_once()
    assert complete.await_args.kwargs["tenant_scope"] == pending_scope
    assert complete.await_args.kwargs["actor_staff_user_id"] == 5
    assert complete.await_args.kwargs["actor_username"] == "tenant-owner"


def test_legacy_google_oauth_state_keeps_membership_for_callback(monkeypatch):
    from routers import manager_google_auth

    request = SimpleNamespace(
        session={
            manager_google_auth.GOOGLE_OAUTH_SESSION_KEY: {
                "state": "expected-state",
                "issued_at": 100.0,
                "redirect_uri": "http://test/api/manager/google-auth/callback",
                "auth_source": "staff_password",
                "auth_version": 4,
                "staff_user_id": 5,
                "username": "tenant-owner",
                "tenant_membership_id": 31,
                "tenant_id": 21,
            }
        }
    )
    monkeypatch.setattr(manager_google_auth, "_oauth_now", lambda: 101.0)
    monkeypatch.setattr(
        manager_google_auth,
        "_google_oauth_redirect_uri",
        lambda _request: "http://test/api/manager/google-auth/callback",
    )

    pending = manager_google_auth._consume_google_oauth_state(
        request,
        "expected-state",
    )

    assert pending is not None
    assert pending["tenant_membership_id"] == 31
    assert pending["tenant_id"] == 21
