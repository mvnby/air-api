"""Browser consent protocol through the complete application middleware."""

import re
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from sqlalchemy import select

from core.security import create_access_token
from models.connector_auth import ConnectorConsent, ConnectorGrant, now_utc
from models.staff import StaffUser
from models.tenancy import TenantMembership
from services.connector_auth_policy import CLIENT_ID, pkce, resource

AUTHORIZE = "/api/connector/oauth/authorize"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"


@pytest.fixture
async def consent_client(async_client, db):
    staff = StaffUser(
        username="consent-browser-manager",
        display_name="Consent Browser Manager",
        primary_role="admin",
        roles=["admin"],
    )
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="admin"))
    await db.commit()
    claims = {
        "sub": staff.username,
        "auth_source": "staff",
        "staff_user_id": staff.id,
        "auth_version": 1,
        "jti": "original-browser-session",
    }
    async_client.cookies.set("access_token", "Bearer " + create_access_token(claims))
    return async_client, claims


async def screen(client, state="browser-state", redirect=CALLBACK):
    response = await client.get(
        AUTHORIZE,
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": redirect,
            "resource": resource(),
            "scope": "kitlane:read",
            "state": state,
            "code_challenge": pkce("v" * 64),
            "code_challenge_method": "S256",
            "response_type": "code",
        },
    )
    assert response.status_code == 200
    form = {
        key: re.search(rf'name="{key}" value="([^"]+)"', response.text).group(1)
        for key in ("consent_id", "csrf_token")
    }
    return response, {**form, "decision": "allow"}


async def grant_count(db):
    return len((await db.execute(select(ConnectorGrant.id))).scalars().all())


@pytest.mark.asyncio
async def test_consent_page_permits_registered_oauth_callback(consent_client):
    client, _ = consent_client
    response, form = await screen(client)
    policy = response.headers["content-security-policy"]
    sources = re.search(r"form-action ([^;]+)", policy).group(1).split()
    assert "'self'" in sources
    assert CALLBACK in sources
    assert "*" not in sources and "https:" not in sources
    assert "default-src 'none'" in policy and "frame-ancestors 'none'" in policy
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    accepted = await client.post(AUTHORIZE, data=form)
    assert accepted.status_code == 303
    assert urlsplit(accepted.headers["location"]).netloc == "chatgpt.com"


@pytest.mark.asyncio
async def test_two_open_consent_pages_are_independent(consent_client, db):
    client, _ = consent_client
    _, first = await screen(client, state="first-tab")
    _, second = await screen(client, state="second-tab")
    assert first["csrf_token"] != second["csrf_token"]
    for form, expected_state in ((first, "first-tab"), (second, "second-tab")):
        accepted = await client.post(AUTHORIZE, data=form)
        assert accepted.status_code == 303
        assert parse_qs(urlsplit(accepted.headers["location"]).query)["state"] == [
            expected_state
        ]
    assert await grant_count(db) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_cookie", ["missing", "stale"])
async def test_consent_does_not_depend_on_shared_cookie(consent_client, legacy_cookie):
    client, _ = consent_client
    _, form = await screen(client)
    client.cookies.delete("kitlane_connector_consent")
    if legacy_cookie == "stale":
        client.cookies.set(
            "kitlane_connector_consent",
            "old-page-nonce",
            domain="test.local",
            path=AUTHORIZE,
        )
    accepted = await client.post(AUTHORIZE, data=form)
    assert accepted.status_code == 303


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["missing", "tampered", "mixed", "session", "expired"]
)
async def test_consent_still_rejects_invalid_binding(consent_client, db, change):
    client, claims = consent_client
    _, form = await screen(client)
    if change == "missing":
        form.pop("csrf_token")
    elif change == "tampered":
        form["csrf_token"] += "-changed"
    elif change == "mixed":
        _, other = await screen(client, state="another-consent")
        form["csrf_token"] = other["csrf_token"]
    elif change == "session":
        claims["jti"] = "different-browser-session"
        client.cookies.set("access_token", "Bearer " + create_access_token(claims))
    else:
        pending = (
            await db.execute(
                select(ConnectorConsent).where(
                    ConnectorConsent.id == form["consent_id"]
                )
            )
        ).scalar_one()
        pending.expires_at = now_utc() - timedelta(seconds=1)
        await db.commit()
    denied = await client.post(AUTHORIZE, data=form)
    assert denied.status_code == 403
    assert denied.json()["error"] == "invalid_request"
    assert await grant_count(db) == 0


@pytest.mark.asyncio
async def test_consent_is_single_use_without_shared_cookie(consent_client, db):
    client, _ = consent_client
    _, form = await screen(client)
    assert (await client.post(AUTHORIZE, data=form)).status_code == 303
    assert (await client.post(AUTHORIZE, data=form)).status_code == 403
    assert await grant_count(db) == 1


@pytest.mark.asyncio
async def test_duplicate_form_token_cannot_create_grant(consent_client, db):
    client, _ = consent_client
    _, form = await screen(client)
    denied = await client.post(
        AUTHORIZE,
        content=urlencode(form) + "&csrf_token=duplicate",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert denied.status_code == 400
    assert denied.json()["error_description"] == "Duplicate form parameters"
    assert await grant_count(db) == 0
