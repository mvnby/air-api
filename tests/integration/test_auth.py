import pytest
from httpx import AsyncClient
from core.config import settings
from models import StaffUser, TenantMembership
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
        password_hash=StaffUserService.hash_password("secret123"),
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
        data={"username": "manager", "password": "secret123"},
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
