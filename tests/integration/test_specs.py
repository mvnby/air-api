import pytest
from httpx import AsyncClient
from sqlmodel import select
from models import Product
from core.config import settings

@pytest.mark.asyncio
async def test_get_public_spec_keys(async_client: AsyncClient, db):
    """
    Test public endpoint GET /api/v1/specs/keys.
    - Create 2 products in the DB with different specs.
    - Assert: Status 200. Response contains keys ["color", "size"].
    """
    # 1. Setup: Create 2 products
    p1 = Product(
        title="Product 1",
        slug="product-1",
        price=1000,
        area=25,
        specs={"color": "red"}
    )
    p2 = Product(
        title="Product 2",
        slug="product-2",
        price=2000,
        area=35,
        specs={"color": "blue", "size": "M"}
    )
    db.add(p1)
    db.add(p2)
    await db.commit()

    # 2. Action: Call GET /api/v1/specs/keys
    response = await async_client.get("/api/v1/specs/keys")

    # 3. Verification
    assert response.status_code == 200
    data = response.json()
    assert "keys" in data
    assert sorted(data["keys"]) == sorted(["color", "size"])
    assert data["total_products_using"]["color"] == 2
    assert data["total_products_using"]["size"] == 1

@pytest.mark.asyncio
async def test_bulk_update_unauthorized(async_client: AsyncClient):
    """
    Test Bulk Update Security.
    - Attempt to POST /api/manager/specs/bulk-update without an auth token.
    - Assert: Status 401 Unauthorized.
    """
    payload = {
        "product_ids": [1, 2],
        "specs": {"wifi": "yes"},
        "operation": "merge"
    }
    response = await async_client.post("/api/manager/specs/bulk-update", json=payload)
    
    # fastapi get_current_username raises 401
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_bulk_update_logic(async_client: AsyncClient, db):
    """
    Test Bulk Update Logic.
    - Create 3 products.
    - Login as admin to get a valid access token.
    - Send POST /api/manager/specs/bulk-update (merge).
    - Verification: All products have merged specs.
    """
    # 1. Setup: Create 3 products
    products = [
        Product(title=f"P{i}", slug=f"p-{i}", price=100*i, area=20, specs={"old": "val"})
        for i in range(1, 4)
    ]
    for p in products:
        db.add(p)
    await db.commit()
    for p in products:
        await db.refresh(p)
    
    product_ids = [p.id for p in products]

    # 2. Hero Login (Get token)
    login_payload = {
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    }
    login_resp = await async_client.post("/login/access-token", data=login_payload)
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    
    # 3. Action: Bulk Update
    headers = {"Authorization": f"Bearer {token}"}
    update_payload = {
        "product_ids": product_ids,
        "specs": {"wifi": "yes", "warranty": "3 years"},
        "operation": "merge"
    }
    response = await async_client.post(
        "/api/manager/specs/bulk-update", 
        json=update_payload, 
        headers=headers
    )
    
    assert response.status_code == 200
    
    # 4. Verify DB
    for pid in product_ids:
        # Clear session to avoid caching
        db.expire_all()
        p = await db.get(Product, pid)
        assert p.specs["wifi"] == "yes"
        assert p.specs["warranty"] == "3 years"
        assert p.specs["old"] == "val"
