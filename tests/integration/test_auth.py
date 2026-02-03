import pytest
from httpx import AsyncClient
from core.config import settings

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
async def test_access_protected_route_without_token(async_client: AsyncClient):
    """Test accessing a protected admin route without authentication."""
    # Using a known admin route, e.g., /admin/ (from SQLAdmin) or an API route if available
    # Checking routers/api.py, /api/admin/proxy/egr is protected by get_current_username
    
    response = await async_client.get("/api/admin/proxy/egr?unp=100100100")
    
    # Expect 401 Unauthorized (or 403 depending on implementation)
    # create_access_token / get_current_username usually raises 401
    assert response.status_code in [401, 403]
