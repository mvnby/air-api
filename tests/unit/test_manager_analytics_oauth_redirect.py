from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.tenancy import TenantScope
from routers import manager_analytics_connections
from services.analytics_oauth_state import ANALYTICS_GOOGLE_OAUTH_SESSION_KEY


def _auth():
    return SimpleNamespace(
        tenant_scope=lambda: TenantScope(tenant_id=2, storefront_id=7),
        auth_source="staff",
        auth_version=3,
        staff_user_id=42,
        username="owner",
        tenant_membership_id=8,
    )


def test_analytics_google_oauth_starts_with_production_callback(monkeypatch):
    runtime_settings = SimpleNamespace(
        is_production=True,
        MANAGER_BASE_URL="https://api.mvn.by/manager",
        GOOGLE_OAUTH_REDIRECT_URI=(
            "https://api.mvn.by/api/manager/google-auth/callback"
        ),
        GOOGLE_ADS_DEVELOPER_TOKEN="",
    )
    request = SimpleNamespace(
        session={},
        url_for=lambda _name: "http://internal/api/manager/google-auth/callback",
    )
    seen = {}

    def build_url(provider, redirect_uri, state):
        seen.update(provider=provider, redirect_uri=redirect_uri, state=state)
        return "https://accounts.google.com/o/oauth2/auth"

    monkeypatch.setattr(manager_analytics_connections, "settings", runtime_settings)
    monkeypatch.setattr(manager_analytics_connections, "build_authorization_url", build_url)

    response = manager_analytics_connections._start_google_authorization(
        request,
        auth=_auth(),
        provider="google_analytics",
        public_config={"property_id": "123456"},
    )

    expected = "https://api.mvn.by/api/manager/google-auth/callback"
    assert response.url == "https://accounts.google.com/o/oauth2/auth"
    assert seen["redirect_uri"] == expected
    assert request.session[ANALYTICS_GOOGLE_OAUTH_SESSION_KEY]["redirect_uri"] == expected


def test_analytics_google_oauth_derives_production_callback(monkeypatch):
    runtime_settings = SimpleNamespace(
        is_production=True,
        MANAGER_BASE_URL="https://api.mvn.by/manager",
        GOOGLE_OAUTH_REDIRECT_URI="",
        GOOGLE_ADS_DEVELOPER_TOKEN="",
    )
    request = SimpleNamespace(
        session={},
        url_for=lambda _name: "http://internal/api/manager/google-auth/callback",
    )
    seen = {}

    def build_url(provider, redirect_uri, state):
        seen.update(provider=provider, redirect_uri=redirect_uri, state=state)
        return "https://accounts.google.com/o/oauth2/auth"

    monkeypatch.setattr(manager_analytics_connections, "settings", runtime_settings)
    monkeypatch.setattr(manager_analytics_connections, "build_authorization_url", build_url)

    manager_analytics_connections._start_google_authorization(
        request,
        auth=_auth(),
        provider="google_analytics",
        public_config={"property_id": "123456"},
    )

    expected = "https://api.mvn.by/api/manager/google-auth/callback"
    assert seen["redirect_uri"] == expected
    assert request.session[ANALYTICS_GOOGLE_OAUTH_SESSION_KEY]["redirect_uri"] == expected


def test_analytics_google_oauth_rejects_localhost_in_production(monkeypatch):
    runtime_settings = SimpleNamespace(
        is_production=True,
        MANAGER_BASE_URL="https://api.mvn.by/manager",
        GOOGLE_OAUTH_REDIRECT_URI=(
            "http://127.0.0.1:8000/api/manager/google-auth/callback"
        ),
        GOOGLE_ADS_DEVELOPER_TOKEN="",
    )
    request = SimpleNamespace(
        session={},
        url_for=lambda _name: "http://internal/api/manager/google-auth/callback",
    )
    monkeypatch.setattr(manager_analytics_connections, "settings", runtime_settings)

    with pytest.raises(HTTPException) as error:
        manager_analytics_connections._start_google_authorization(
            request,
            auth=_auth(),
            provider="google_analytics",
            public_config={"property_id": "123456"},
        )

    assert error.value.status_code == 503
    assert ANALYTICS_GOOGLE_OAUTH_SESSION_KEY not in request.session
