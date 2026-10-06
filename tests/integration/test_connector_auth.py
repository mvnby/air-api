"""Exercise real durable OAuth state and existing live Manager authorization."""

import asyncio
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, create_access_token, require_manager_access
from models.connector_auth import (
    ConnectorAuthorizationCode,
    ConnectorGrant,
    ConnectorToken,
    now_utc,
)
from models.staff import StaffUser
from models.tenancy import Tenant, TenantMembership
from routers.connector_auth import router
from services.connector_auth_policy import (
    CLIENT_ID,
    ConnectorAuthError,
    digest,
    pkce,
    resource,
)
from services.connector_auth_service import ConnectorAuthService as Auth

REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "s" * 64


@pytest.fixture
async def identity(db):
    user = StaffUser(
        display_name="Connector Manager",
        username="connector-manager",
        primary_role="admin",
        roles=["admin"],
    )
    db.add(user)
    await db.flush()
    membership = TenantMembership(tenant_id=1, staff_user_id=user.id, role="admin")
    db.add(membership)
    await db.commit()
    auth = AuthenticatedUser(
        username=user.username,
        auth_source="staff",
        staff_user_id=user.id,
        role="admin",
        tenant_id=1,
        storefront_id=1,
        tenant_membership_id=membership.id,
        is_system_tenant=True,
        auth_version=1,
    )
    return user, membership, auth


async def consent_code(db, identity, *, scopes="kitlane:read kitlane:incoming:write"):
    pending, nonce = await Auth.start_consent(
        db,
        identity[2],
        "manager-session",
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        scope=scopes,
        state="opaque-state",
        code_challenge=pkce(VERIFIER),
        code_challenge_method="S256",
        response_type="code",
    )
    url = await Auth.finish_consent(
        db,
        identity[2],
        "manager-session",
        consent_id=pending.id,
        nonce=nonce,
        allow=True,
    )
    query = parse_qs(urlsplit(url).query)
    assert query["state"] == ["opaque-state"]
    assert query["iss"] == ["https://api.mvn.by"]
    return query["code"][0]


async def tokens(db, identity):
    code = await consent_code(db, identity)
    return await Auth.exchange_code(
        db,
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        code_verifier=VERIFIER,
    )


@pytest.mark.asyncio
async def test_oauth_success_hashes_scope_and_single_use(db, identity):
    code = await consent_code(db, identity)
    result = await Auth.exchange_code(
        db,
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        code_verifier=VERIFIER,
    )
    actor = await Auth.resolve_actor(db, result.access_token, "kitlane:incoming:write")
    assert actor.staff_user_id == identity[0].id
    assert actor.channel == "chatgpt" and actor.tenant_scope.tenant_id == 1
    stored = (await db.execute(select(ConnectorToken))).scalars().all()
    assert {row.token_hash for row in stored} == {
        digest(result.access_token),
        digest(result.refresh_token),
    }
    assert all(result.access_token not in repr(row) for row in stored)
    with pytest.raises(ConnectorAuthError, match="consumed"):
        await Auth.exchange_code(
            db,
            code=code,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT,
            requested_resource=resource(),
            code_verifier=VERIFIER,
        )
    await db.rollback()
    with pytest.raises(ConnectorAuthError) as error:
        await Auth.resolve_actor(db, result.access_token, "kitlane:tasks:write")
    assert error.value.error == "insufficient_scope"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "client",
        "resource",
        "redirect",
        "pkce",
        "plain",
        "scope",
        "write_only",
        "legacy",
    ],
)
async def test_invalid_authorization_request(db, identity, change):
    kwargs = dict(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        scope="kitlane:read",
        state="state",
        code_challenge=pkce(VERIFIER),
        code_challenge_method="S256",
        response_type="code",
    )
    if change == "client":
        kwargs["client_id"] = "attacker"
    if change == "resource":
        kwargs["requested_resource"] = "https://evil.example/mcp"
    if change == "redirect":
        kwargs["redirect_uri"] = REDIRECT + "?next=evil"
    if change == "pkce":
        kwargs["code_challenge"] = "short"
    if change == "plain":
        kwargs["code_challenge_method"] = "plain"
    if change == "scope":
        kwargs["scope"] = "kitlane:admin"
    if change == "write_only":
        kwargs["scope"] = "kitlane:tasks:write"
    auth = (
        identity[2]
        if change != "legacy"
        else AuthenticatedUser(
            username="owner",
            auth_source="legacy",
            role="owner",
            tenant_id=1,
            storefront_id=1,
        )
    )
    with pytest.raises(ConnectorAuthError):
        await Auth.start_consent(db, auth, "session", **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["pkce", "client", "resource", "redirect", "expired"]
)
async def test_invalid_code_exchange(db, identity, change):
    code = await consent_code(db, identity)
    kwargs = dict(
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        code_verifier=VERIFIER,
    )
    if change == "pkce":
        kwargs["code_verifier"] = "x" * 64
    if change == "client":
        kwargs["client_id"] = "attacker"
    if change == "resource":
        kwargs["requested_resource"] += "/other"
    if change == "redirect":
        kwargs["redirect_uri"] += "/other"
    if change == "expired":
        row = (await db.execute(select(ConnectorAuthorizationCode))).scalar_one()
        row.expires_at = now_utc() - timedelta(seconds=1)
        await db.commit()
    with pytest.raises(ConnectorAuthError):
        await Auth.exchange_code(db, **kwargs)


@pytest.mark.asyncio
async def test_refresh_rotation_and_replay_revokes_entire_grant(db, identity):
    original = await tokens(db, identity)
    rotated = await Auth.refresh(
        db,
        refresh_token=original.refresh_token,
        client_id=CLIENT_ID,
        requested_resource=resource(),
    )
    assert original.refresh_token != rotated.refresh_token
    await Auth.resolve_actor(db, rotated.access_token, "kitlane:read")
    with pytest.raises(ConnectorAuthError, match="replay"):
        await Auth.refresh(
            db,
            refresh_token=original.refresh_token,
            client_id=CLIENT_ID,
            requested_resource=resource(),
        )
    for value in (original.access_token, rotated.access_token):
        with pytest.raises(ConnectorAuthError, match="revoked"):
            await Auth.resolve_actor(db, value, "kitlane:read")


@pytest.mark.asyncio
async def test_wrong_client_resource_expired_refresh_and_foreign_grant(db, identity):
    result = await tokens(db, identity)
    with pytest.raises(ConnectorAuthError):
        await Auth.refresh(
            db,
            refresh_token=result.refresh_token,
            client_id="attacker",
            requested_resource=resource(),
        )
    with pytest.raises(ConnectorAuthError):
        await Auth.refresh(
            db,
            refresh_token=result.refresh_token,
            client_id=CLIENT_ID,
            requested_resource="https://evil.example",
        )
    grant_id = (await db.execute(select(ConnectorGrant.id))).scalar_one()
    foreign = AuthenticatedUser(
        username="other",
        auth_source="staff",
        staff_user_id=identity[0].id + 1,
        tenant_id=1,
        storefront_id=1,
        role="manager",
    )
    with pytest.raises(ConnectorAuthError):
        await Auth.revoke_grant(db, foreign, grant_id)
    await Auth.resolve_actor(db, result.access_token, "kitlane:read")
    row = (
        await db.execute(select(ConnectorToken).where(ConnectorToken.kind == "refresh"))
    ).scalar_one()
    row.expires_at = now_utc() - timedelta(seconds=1)
    await db.commit()
    with pytest.raises(ConnectorAuthError, match="expired"):
        await Auth.refresh(
            db,
            refresh_token=result.refresh_token,
            client_id=CLIENT_ID,
            requested_resource=resource(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["code", "refresh"])
async def test_concurrent_reuse_across_physical_connections(db_engine, flow):
    # Committed setup is visible to genuinely independent PostgreSQL sessions.
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        user = StaffUser(
            display_name="Concurrent",
            username="concurrent",
            primary_role="manager",
            roles=["manager"],
        )
        setup.add(user)
        await setup.flush()
        membership = TenantMembership(
            tenant_id=1, staff_user_id=user.id, role="manager"
        )
        setup.add(membership)
        await setup.commit()
        auth = AuthenticatedUser(
            username=user.username,
            auth_source="staff",
            staff_user_id=user.id,
            role="manager",
            tenant_id=1,
            storefront_id=1,
            tenant_membership_id=membership.id,
            is_system_tenant=True,
            auth_version=1,
        )
        identity = (user, membership, auth)
        code = await consent_code(setup, identity)
        if flow == "refresh":
            issued = await Auth.exchange_code(
                setup,
                code=code,
                client_id=CLIENT_ID,
                redirect_uri=REDIRECT,
                requested_resource=resource(),
                code_verifier=VERIFIER,
            )

    async def execute():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            try:
                if flow == "code":
                    return await Auth.exchange_code(
                        session,
                        code=code,
                        client_id=CLIENT_ID,
                        redirect_uri=REDIRECT,
                        requested_resource=resource(),
                        code_verifier=VERIFIER,
                    )
                return await Auth.refresh(
                    session,
                    refresh_token=issued.refresh_token,
                    client_id=CLIENT_ID,
                    requested_resource=resource(),
                )
            except ConnectorAuthError as error:
                await session.rollback()
                return error

    results = await asyncio.wait_for(asyncio.gather(execute(), execute()), timeout=10)
    assert sum(not isinstance(result, ConnectorAuthError) for result in results) == 1
    async with AsyncSession(db_engine) as check:
        grants = (await check.execute(select(ConnectorGrant))).scalars().all()
        assert len(grants) == 1
        if flow == "refresh":
            assert grants[0].revoked_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["role", "demo"])
async def test_live_recheck_refreshes_cached_security_rows(db_engine, change):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        user = StaffUser(
            display_name="Cached",
            username="cached",
            primary_role="admin",
            roles=["admin"],
        )
        session.add(user)
        await session.flush()
        membership = TenantMembership(tenant_id=1, staff_user_id=user.id, role="admin")
        session.add(membership)
        await session.commit()
        auth = AuthenticatedUser(
            username=user.username,
            auth_source="staff",
            staff_user_id=user.id,
            role="admin",
            tenant_id=1,
            storefront_id=1,
            tenant_membership_id=membership.id,
            is_system_tenant=True,
            auth_version=1,
        )
        issued = await tokens(session, (user, membership, auth))
        await Auth.resolve_actor(session, issued.access_token, "kitlane:read")
        async with AsyncSession(db_engine) as external:
            if change == "role":
                await external.execute(
                    update(TenantMembership)
                    .where(TenantMembership.id == membership.id)
                    .values(role="manager")
                )
            else:
                await external.execute(
                    update(Tenant).where(Tenant.id == 1).values(demo_read_only=True)
                )
            await external.commit()
        with pytest.raises(ConnectorAuthError):
            await Auth.resolve_actor(session, issued.access_token, "kitlane:read")


@pytest.mark.asyncio
async def test_cached_refresh_cannot_hide_consumption_by_another_session(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        user = StaffUser(
            display_name="Refresh Cache",
            username="refresh-cache",
            primary_role="manager",
            roles=["manager"],
        )
        session.add(user)
        await session.flush()
        membership = TenantMembership(
            tenant_id=1, staff_user_id=user.id, role="manager"
        )
        session.add(membership)
        await session.commit()
        auth = AuthenticatedUser(
            username=user.username,
            auth_source="staff",
            staff_user_id=user.id,
            role="manager",
            tenant_id=1,
            storefront_id=1,
            tenant_membership_id=membership.id,
            is_system_tenant=True,
            auth_version=1,
        )
        issued = await tokens(session, (user, membership, auth))
        # Hold a strong reference: the original session must really cache this row.
        cached = (
            await session.execute(
                select(ConnectorToken).where(
                    ConnectorToken.token_hash == digest(issued.refresh_token)
                )
            )
        ).scalar_one()
        assert cached.consumed_at is None
        async with AsyncSession(db_engine, expire_on_commit=False) as external:
            rotated = await Auth.refresh(
                external,
                refresh_token=issued.refresh_token,
                client_id=CLIENT_ID,
                requested_resource=resource(),
            )
        assert cached.consumed_at is None
        with pytest.raises(ConnectorAuthError, match="replay"):
            await Auth.refresh(
                session,
                refresh_token=issued.refresh_token,
                client_id=CLIENT_ID,
                requested_resource=resource(),
            )
        with pytest.raises(ConnectorAuthError):
            await Auth.resolve_actor(session, rotated.access_token, "kitlane:read")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "inactive",
        "auth_version",
        "membership",
        "role",
        "must_change_password",
        "revoke",
        "expired",
    ],
)
async def test_live_access_recheck(db, identity, change):
    result = await tokens(db, identity)
    user, membership, auth = identity
    if change == "inactive":
        user.status = "inactive"
    if change == "auth_version":
        user.auth_version += 1
    if change == "membership":
        membership.status = "disabled"
    if change == "role":
        membership.role = "manager"
    if change == "must_change_password":
        user.must_change_password = True
    if change == "revoke":
        await Auth.revoke_grant(
            db, auth, (await db.execute(select(ConnectorGrant.id))).scalar_one()
        )
    if change == "expired":
        row = (
            await db.execute(
                select(ConnectorToken).where(ConnectorToken.kind == "access")
            )
        ).scalar_one()
        row.expires_at = now_utc() - timedelta(seconds=1)
    await db.commit()
    with pytest.raises(ConnectorAuthError):
        await Auth.resolve_actor(db, result.access_token, "kitlane:read")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["csrf", "session", "replay"])
async def test_consent_csrf_session_and_replay(db, identity, change):
    pending, nonce = await Auth.start_consent(
        db,
        identity[2],
        "session",
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        scope="kitlane:read",
        state="state",
        code_challenge=pkce(VERIFIER),
        code_challenge_method="S256",
        response_type="code",
    )
    if change == "replay":
        await Auth.finish_consent(
            db, identity[2], "session", consent_id=pending.id, nonce=nonce, allow=True
        )
    with pytest.raises(ConnectorAuthError):
        await Auth.finish_consent(
            db,
            identity[2],
            "evil" if change == "session" else "session",
            consent_id=pending.id,
            nonce="evil" if change == "csrf" else nonce,
            allow=True,
        )


@pytest.mark.asyncio
async def test_consent_denial_never_issues_grant(db, identity):
    pending, nonce = await Auth.start_consent(
        db,
        identity[2],
        "session",
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        requested_resource=resource(),
        scope="kitlane:read",
        state="state",
        code_challenge=pkce(VERIFIER),
        code_challenge_method="S256",
        response_type="code",
    )
    url = await Auth.finish_consent(
        db, identity[2], "session", consent_id=pending.id, nonce=nonce, allow=False
    )
    query = parse_qs(urlsplit(url).query)
    assert query["error"] == ["access_denied"] and query["state"] == ["state"]
    assert (await db.execute(select(ConnectorGrant))).scalars().all() == []


@pytest.mark.asyncio
async def test_http_flow_discovery_csrf_and_manager_token_separation(db, identity):
    app = FastAPI()
    app.include_router(router)

    async def override():
        yield db

    app.dependency_overrides[get_session] = override

    @app.get("/manager-protected")
    async def protected(auth=Depends(require_manager_access)):
        return {"username": auth.username}

    jwt = create_access_token(
        {
            "sub": identity[0].username,
            "auth_source": "staff",
            "staff_user_id": identity[0].id,
            "auth_version": 1,
        }
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        client.cookies.set("access_token", "Bearer " + jwt)
        metadata = await client.get("/.well-known/oauth-authorization-server")
        assert metadata.json()["code_challenge_methods_supported"] == ["S256"]
        params = dict(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT,
            resource=resource(),
            scope="kitlane:read",
            state="state",
            code_challenge=pkce(VERIFIER),
            code_challenge_method="S256",
            response_type="code",
        )
        screen = await client.get("/api/connector/oauth/authorize", params=params)
        assert screen.status_code == 200
        consent_id = re.search(r'name="consent_id" value="([^"]+)"', screen.text).group(
            1
        )
        nonce = re.search(r'name="csrf_token" value="([^"]+)"', screen.text).group(1)
        bad = await client.post(
            "/api/connector/oauth/authorize",
            data={"consent_id": consent_id, "csrf_token": "bad", "decision": "allow"},
        )
        assert bad.status_code == 403
        accepted = await client.post(
            "/api/connector/oauth/authorize",
            data={"consent_id": consent_id, "csrf_token": nonce, "decision": "allow"},
        )
        assert accepted.status_code == 303
        code = parse_qs(urlsplit(accepted.headers["location"]).query)["code"][0]
        issued = await client.post(
            "/api/connector/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT,
                "resource": resource(),
                "code_verifier": VERIFIER,
            },
        )
        assert (
            issued.status_code == 200 and issued.headers["cache-control"] == "no-store"
        )
        forbidden = await client.get(
            "/manager-protected",
            headers={"Authorization": "Bearer " + issued.json()["access_token"]},
        )
        assert forbidden.status_code == 401
        listed = await client.get("/api/manager/connector/grants")
        grant_id = listed.json()["items"][0]["id"]
        denied = await client.post(f"/api/manager/connector/grants/{grant_id}/revoke")
        assert denied.status_code == 403
        revoked = await client.post(
            f"/api/manager/connector/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": listed.json()["csrf_token"]},
        )
        assert revoked.status_code == 204
