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


async def screen(client, state="browser-state", redirect=CALLBACK, scopes="kitlane:read"):
    response = await client.get(
        AUTHORIZE,
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": redirect,
            "resource": resource(),
            "scope": scopes,
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


@pytest.mark.asyncio
async def test_login_redirect_preserves_only_valid_oauth_request(consent_client, db):
    client, _ = consent_client
    client.cookies.clear()
    params = dict(client_id=CLIENT_ID, redirect_uri=CALLBACK, resource=resource(),
                  scope="kitlane:read", state="resume-after-login",
                  code_challenge=pkce("v" * 64), code_challenge_method="S256",
                  response_type="code")
    response = await client.get(AUTHORIZE, params=params, follow_redirects=False)
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/manager/" and not location.netloc
    target = parse_qs(location.query)["connector_return"][0]
    assert urlsplit(target).path == AUTHORIZE
    assert parse_qs(urlsplit(target).query)["state"] == ["resume-after-login"]
    assert await grant_count(db) == 0
    assert not (await db.execute(select(ConnectorConsent.id))).scalars().all()
    params["redirect_uri"] = "https://evil.example/callback"
    rejected = await client.get(AUTHORIZE, params=params, follow_redirects=False)
    assert rejected.status_code == 400 and "location" not in rejected.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("account", ["legacy", "temporary_password"])
async def test_existing_unusable_session_returns_to_personal_login(consent_client, db, account):
    client, claims = consent_client
    if account == "legacy":
        from core.config import settings
        claims = {"sub": settings.ADMIN_USERNAME, "auth_source": "legacy", "legacy_auth_version": 1}
        client.cookies.set("access_token", "Bearer " + create_access_token(claims))
    else:
        user = await db.get(StaffUser, claims["staff_user_id"])
        user.must_change_password = True
        await db.commit()
    response = await client.get(AUTHORIZE, params={"client_id": CLIENT_ID,
        "redirect_uri": CALLBACK, "resource": resource(), "scope": "kitlane:read",
        "state": "personal-login", "code_challenge": pkce("v" * 64),
        "code_challenge_method": "S256", "response_type": "code"}, follow_redirects=False)
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/manager/"
    assert not (await db.execute(select(ConnectorConsent.id))).scalars().all()
    assert await grant_count(db) == 0


@pytest.mark.asyncio
async def test_company_and_independent_permissions_are_visible(consent_client):
    client, _ = consent_client
    response, _ = await screen(client, scopes="kitlane:read kitlane:mail:read kitlane:mail:drafts:write kitlane:mail:send")
    assert "Мастер Воздуха" in response.text
    assert "Компания определена по вашей учётной записи" in response.text
    assert "Это не разрешает отправку" in response.text
    assert 'name="scope:kitlane:mail:send" value="allow">' in response.text
    assert 'name="scope:kitlane:mail:read" value="allow" checked>' in response.text


@pytest.mark.asyncio
async def test_selected_scopes_reach_actual_tokens_and_exclude_send(consent_client, db):
    from services.connector_auth_service import ConnectorAuthService
    client, _ = consent_client
    _, form = await screen(client, scopes="kitlane:read kitlane:mail:read kitlane:mail:drafts:write kitlane:mail:send")
    form.update(scope_selection="explicit", **{"scope:kitlane:mail:read": "allow", "scope:kitlane:mail:drafts:write": "allow"})
    response = await client.post(AUTHORIZE, data=form)
    assert response.status_code == 303
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    token = await ConnectorAuthService.exchange_code(db, code=code, client_id=CLIENT_ID,
        redirect_uri=CALLBACK, requested_resource=resource(), code_verifier="v" * 64)
    assert set(token.scope.split()) == {"kitlane:read", "kitlane:mail:read", "kitlane:mail:drafts:write"}
    from services.connector_auth_policy import ConnectorAuthError
    with pytest.raises(ConnectorAuthError) as error:
        await ConnectorAuthService.resolve_actor(db, token.access_token, "kitlane:mail:send")
    assert error.value.error == "insufficient_scope"


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", ["kitlane:mail:send", "kitlane:admin"])
async def test_selection_cannot_add_unrequested_or_unknown_permissions(consent_client, db, permission):
    client, _ = consent_client
    _, form = await screen(client)
    form.update(scope_selection="explicit", **{"scope:" + permission: "allow"})
    response = await client.post(AUTHORIZE, data=form)
    assert response.status_code == 400 and response.json()["error"] == "invalid_scope"
    assert await grant_count(db) == 0


@pytest.mark.asyncio
async def test_omitting_selection_does_not_restore_unchecked_send_permission(consent_client, db):
    client, _ = consent_client
    _, form = await screen(client, scopes="kitlane:read kitlane:mail:send")
    assert (await client.post(AUTHORIZE, data=form)).status_code == 303
    grant = (await db.execute(select(ConnectorGrant))).scalars().one()
    assert grant.scopes == ["kitlane:read"]


@pytest.mark.asyncio
async def test_pending_pre_upgrade_form_can_finish_with_basic_read(consent_client, db):
    from services.connector_auth_policy import digest
    client, _ = consent_client
    _, form = await screen(client, scopes="kitlane:read kitlane:mail:send")
    pending = (await db.execute(select(ConnectorConsent).where(ConnectorConsent.id == form["consent_id"]))).scalars().one()
    pending.csrf_hash = digest(form["csrf_token"])
    await db.commit()
    assert (await client.post(AUTHORIZE, data=form)).status_code == 303
    grant = (await db.execute(select(ConnectorGrant))).scalars().one()
    assert grant.scopes == ["kitlane:read"]


@pytest.mark.asyncio
async def test_reading_own_consent_cannot_choose_another_company(consent_client, db):
    client, _ = consent_client
    _, form = await screen(client)
    form.update(tenant_id="999", storefront_id="999")
    assert (await client.post(AUTHORIZE, data=form)).status_code == 303
    grant = (await db.execute(select(ConnectorGrant))).scalars().one()
    assert grant.tenant_id == 1 and grant.storefront_id == 1


@pytest.mark.asyncio
async def test_owner_and_manager_in_one_company_have_independent_equal_scope_connections(consent_client, db):
    from services.connector_auth_policy import SCOPES
    client, _ = consent_client
    connections = []
    for role in ("owner", "manager"):
        user = StaffUser(username="partner-" + role, primary_role=role, roles=[role])
        db.add(user)
        await db.flush()
        db.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role=role))
        await db.commit()
        claims = {"sub": user.username, "auth_source": "staff", "staff_user_id": user.id, "auth_version": 1}
        client.cookies.set("access_token", "Bearer " + create_access_token(claims))
        _, form = await screen(client, state="partner-" + role, scopes=" ".join(sorted(SCOPES)))
        form.update(scope_selection="explicit", **{"scope:" + scope: "allow" for scope in SCOPES if scope != "kitlane:read"})
        assert (await client.post(AUTHORIZE, data=form)).status_code == 303
        listed = (await client.get("/api/manager/connector/grants")).json()
        assert len(listed["items"]) == 1
        assert set(listed["items"][0]["scopes"]) == SCOPES
        connections.append((user.id, listed["items"][0]["id"]))
    rejected = await client.post(f"/api/manager/connector/grants/{connections[0][1]}/revoke",
                                 headers={"X-CSRF-Token": listed["csrf_token"]})
    assert rejected.status_code == 403
    grants = (await db.execute(select(ConnectorGrant))).scalars().all()
    assert len(grants) == 2 and all(grant.revoked_at is None for grant in grants)
    assert {grant.staff_user_id for grant in grants} == {user_id for user_id, _ in connections}


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
