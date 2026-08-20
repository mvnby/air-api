import pytest
from httpx import AsyncClient
from core.config import settings
from core.security import create_access_token
from models import LegacyOwnerAuthState, StaffUser, TenantMembership
from services.staff_user_service import StaffUserService

@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    """Test successful login with admin credentials."""
    payload = {
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    }
    response = await async_client.post("/login/access-token", data=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Verify cookie is set
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_login_success_with_staff_user(async_client: AsyncClient, db):
    staff_user = StaffUser(
        display_name="Manager",
        status="active",
        primary_role="manager",
        roles=["manager"],
        username="manager",
        password_hash=StaffUserService.hash_password("secret-12345"),
    )
    db.add(staff_user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff_user.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()

    response = await async_client.post(
        "/login/access-token",
        data={"username": "manager", "password": "secret-12345"},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    me_response = await async_client.get("/api/manager/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["username"] == "manager"
    assert payload["role"] == "manager"
    assert payload["display_name"] == "Manager"
    assert payload["auth_source"] == "staff_password"
    assert payload["tenant_id"] == 1
    assert payload["storefront_id"] == 1
    assert payload["tenant_membership_id"] is not None


@pytest.mark.asyncio
async def test_migrated_owner_shadows_env_password_and_legacy_jwt(
    async_client: AsyncClient,
    db,
):
    staff_password = "migrated-owner-password"
    staff_user = StaffUser(
        display_name="System Owner",
        status="active",
        primary_role="owner",
        roles=["owner"],
        username=StaffUserService.normalize_username(settings.ADMIN_USERNAME),
        password_hash=StaffUserService.hash_password(staff_password),
    )
    db.add(staff_user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff_user.id),
            role="owner",
            status="active",
        )
    )
    state = await db.get(LegacyOwnerAuthState, 1)
    assert state is not None
    state.mode = "staff_shadow"
    state.owner_staff_user_id = int(staff_user.id)
    state.legacy_token_version = 2
    db.add(state)
    await db.commit()

    env_fallback = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert env_fallback.status_code == 400
    assert env_fallback.json()["detail"] == "Incorrect username or password"

    staff_login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": staff_password},
    )
    assert staff_login.status_code == 200
    staff_me = await async_client.get(
        "/api/manager/me",
        headers={
            "Authorization": f"Bearer {staff_login.json()['access_token']}"
        },
    )
    assert staff_me.status_code == 200
    assert staff_me.json()["auth_source"] == "staff_password"
    assert staff_me.json()["staff_user_id"] == int(staff_user.id)
    assert staff_me.json()["role"] == "owner"
    assert staff_me.json()["is_system_tenant"] is True

    old_legacy_token = create_access_token(
        {"sub": settings.ADMIN_USERNAME, "auth_source": "legacy"}
    )
    old_legacy_session = await async_client.get(
        "/api/manager/me",
        headers={"Authorization": f"Bearer {old_legacy_token}"},
    )
    assert old_legacy_session.status_code == 401


@pytest.mark.asyncio
async def test_legacy_mode_prioritizes_env_and_versions_rollback_tokens(
    async_client: AsyncClient,
    db,
):
    staff_user = StaffUser(
        display_name="Dormant Shadow Owner",
        status="active",
        primary_role="owner",
        roles=["owner"],
        username=StaffUserService.normalize_username(settings.ADMIN_USERNAME),
        password_hash=StaffUserService.hash_password("dormant-staff-password"),
        auth_version=4,
    )
    db.add(staff_user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff_user.id),
            role="owner",
            status="active",
        )
    )
    state = await db.get(LegacyOwnerAuthState, 1)
    assert state is not None
    state.mode = "legacy"
    state.owner_staff_user_id = None
    state.legacy_token_version = 3
    db.add(state)
    await db.commit()

    dormant_staff_login = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": "dormant-staff-password",
        },
    )
    assert dormant_staff_login.status_code == 400

    env_login = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert env_login.status_code == 200
    current_me = await async_client.get(
        "/api/manager/me",
        headers={
            "Authorization": f"Bearer {env_login.json()['access_token']}"
        },
    )
    assert current_me.status_code == 200
    assert current_me.json()["auth_source"] == "legacy"

    unversioned = create_access_token(
        {"sub": settings.ADMIN_USERNAME, "auth_source": "legacy"}
    )
    stale_version = create_access_token(
        {
            "sub": settings.ADMIN_USERNAME,
            "auth_source": "legacy",
            "legacy_auth_version": 2,
        }
    )
    for token in (unversioned, stale_version):
        response = await async_client.get(
            "/api/manager/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_bound_shadow_owner_cannot_bypass_rollback_after_rename(
    async_client: AsyncClient,
    db,
):
    staff_password = "renamed-shadow-password"
    staff_user = StaffUser(
        display_name="Renamed Shadow Owner",
        status="active",
        primary_role="owner",
        roles=["owner"],
        username="renamed-shadow-owner",
        password_hash=StaffUserService.hash_password(staff_password),
        auth_version=5,
    )
    db.add(staff_user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff_user.id),
            role="owner",
            status="active",
        )
    )
    state = await db.get(LegacyOwnerAuthState, 1)
    assert state is not None
    state.mode = "legacy"
    state.owner_staff_user_id = int(staff_user.id)
    state.legacy_token_version = 4
    db.add(state)
    await db.commit()

    login = await async_client.post(
        "/login/access-token",
        data={"username": staff_user.username, "password": staff_password},
    )
    assert login.status_code == 400
    assert login.json()["detail"] == "Incorrect username or password"

    stale_staff_token = create_access_token(
        {
            "sub": staff_user.username,
            "staff_user_id": int(staff_user.id),
            "role": "owner",
            "auth_source": "staff_password",
            "auth_version": staff_user.auth_version,
        }
    )
    stale_session = await async_client.get(
        "/api/manager/me",
        headers={"Authorization": f"Bearer {stale_staff_token}"},
    )
    assert stale_session.status_code == 401

@pytest.mark.asyncio
async def test_login_failure(async_client: AsyncClient):
    """Test login with incorrect password."""
    payload = {
        "username": settings.ADMIN_USERNAME,
        "password": "wrongpassword"
    }
    response = await async_client.post("/login/access-token", data=payload)
    
    assert response.status_code == 400
    assert "Incorrect username or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logout_clears_browser_cookie_session(async_client: AsyncClient):
    login_response = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert login_response.status_code == 200

    authenticated_response = await async_client.get("/api/manager/me")
    assert authenticated_response.status_code == 200

    logout_response = await async_client.post("/login/logout")
    assert logout_response.status_code == 204
    assert "access_token=\"\"" in logout_response.headers["set-cookie"]
    assert "Max-Age=0" in logout_response.headers["set-cookie"]

    anonymous_response = await async_client.get("/api/manager/me")
    assert anonymous_response.status_code == 401


@pytest.mark.asyncio
async def test_access_protected_route_without_token(async_client: AsyncClient):
    """Test accessing a protected admin route without authentication."""
    # Checking routers/api.py, /api/admin/proxy/egr is protected by get_current_username.
    
    response = await async_client.get("/api/admin/proxy/egr?unp=100100100")
    
    # Expect 401 Unauthorized (or 403 depending on implementation)
    # create_access_token / get_current_username usually raises 401
    assert response.status_code in [401, 403]
