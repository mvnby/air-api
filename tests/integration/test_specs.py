import pytest
from httpx import AsyncClient
from sqlalchemy import func
from sqlmodel import select
from models import Brand, Product, ProductSeries
from core.config import settings


async def _auth_headers(async_client: AsyncClient) -> dict[str, str]:
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

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


@pytest.mark.asyncio
async def test_bulk_update_specs_creates_and_links_product_series(async_client: AsyncClient, db):
    brand = Brand(title="KINGHOME", slug="kinghome", is_published=True)
    db.add(brand)
    await db.flush()

    products = [
        Product(
            title=f"KINGHOME Cosmo {i}",
            slug=f"kinghome-cosmo-{i}",
            price=1000 * i,
            area=20,
            brand_id=brand.id,
            specs={"brand": "KINGHOME"},
        )
        for i in range(1, 3)
    ]
    db.add_all(products)
    await db.flush()
    brand_id = int(brand.id)
    product_ids = [int(product.id) for product in products]
    await db.commit()

    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await async_client.post(
        "/api/manager/specs/bulk-update",
        json={
            "product_ids": product_ids,
            "specs": {"series": "COSMO inverter R32 WI-FI"},
            "operation": "merge",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    db.expire_all()

    series = (
        await db.execute(
            select(ProductSeries).where(
                ProductSeries.brand_id == brand_id,
                ProductSeries.slug == "cosmo",
            )
        )
    ).scalar_one()
    assert series.title == "COSMO"

    for product_id in product_ids:
        updated = await db.get(Product, product_id)
        assert updated.series_id == series.id


@pytest.mark.asyncio
async def test_bulk_update_specs_moves_product_to_new_series(async_client: AsyncClient, db):
    headers = await _auth_headers(async_client)

    brand = Brand(title="KINGHOME", slug="kinghome", is_published=True)
    db.add(brand)
    await db.flush()

    old_series = ProductSeries(title="COSMO", slug="cosmo", brand_id=brand.id, is_published=True)
    db.add(old_series)
    await db.flush()

    product = Product(
        title="KINGHOME Move Test",
        slug="kinghome-move-test",
        price=1000,
        area=20,
        brand_id=brand.id,
        series_id=old_series.id,
        specs={"brand": "KINGHOME", "series": "COSMO"},
    )
    db.add(product)
    await db.flush()
    brand_id = int(brand.id)
    old_series_id = int(old_series.id)
    product_id = int(product.id)
    await db.commit()

    response = await async_client.post(
        "/api/manager/specs/bulk-update",
        json={
            "product_ids": [product_id],
            "specs": {"series": "LUNA Matt inverter R32 WI-FI"},
            "operation": "merge",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    db.expire_all()

    new_series = (
        await db.execute(
            select(ProductSeries).where(
                ProductSeries.brand_id == brand_id,
                ProductSeries.slug == "luna-matt",
            )
        )
    ).scalar_one()
    updated = await db.get(Product, product_id)
    assert updated.series_id == new_series.id

    old_count = (
        await db.execute(select(func.count(Product.id)).where(Product.series_id == old_series_id))
    ).scalar_one()
    new_count = (
        await db.execute(select(func.count(Product.id)).where(Product.series_id == new_series.id))
    ).scalar_one()
    assert old_count == 0
    assert new_count == 1


@pytest.mark.asyncio
async def test_bulk_update_specs_delete_series_key_clears_series_link(
    async_client: AsyncClient,
    db,
):
    headers = await _auth_headers(async_client)

    brand = Brand(title="KINGHOME Delete Series", slug="kinghome-delete-series-brand", is_published=True)
    db.add(brand)
    await db.flush()

    series = ProductSeries(title="COSMO", slug="cosmo", brand_id=brand.id, is_published=True)
    db.add(series)
    await db.flush()

    product = Product(
        title="KINGHOME Delete Series",
        slug="kinghome-delete-series",
        price=1000,
        area=20,
        brand_id=brand.id,
        series_id=series.id,
        specs={"brand": "KINGHOME", "series": "COSMO", "wifi": "yes"},
    )
    db.add(product)
    await db.flush()
    product_id = int(product.id)
    await db.commit()

    response = await async_client.post(
        "/api/manager/specs/bulk-update",
        json={
            "product_ids": [product_id],
            "specs": {"series": ""},
            "operation": "delete_keys",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    updated = await db.get(Product, product_id)
    assert "series" not in updated.specs
    assert updated.series_id is None


@pytest.mark.asyncio
async def test_bulk_update_specs_replace_without_series_clears_series_link(
    async_client: AsyncClient,
    db,
):
    headers = await _auth_headers(async_client)

    brand = Brand(title="KINGHOME Replace Series", slug="kinghome-replace-series-brand", is_published=True)
    db.add(brand)
    await db.flush()

    series = ProductSeries(title="COSMO", slug="cosmo", brand_id=brand.id, is_published=True)
    db.add(series)
    await db.flush()

    product = Product(
        title="KINGHOME Replace Series",
        slug="kinghome-replace-series",
        price=1200,
        area=25,
        brand_id=brand.id,
        series_id=series.id,
        specs={"brand": "KINGHOME", "series": "COSMO", "wifi": "yes"},
    )
    db.add(product)
    await db.flush()
    product_id = int(product.id)
    await db.commit()

    response = await async_client.post(
        "/api/manager/specs/bulk-update",
        json={
            "product_ids": [product_id],
            "specs": {"brand": "KINGHOME", "wifi": "yes"},
            "operation": "replace",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    updated = await db.get(Product, product_id)
    assert "series" not in updated.specs
    assert updated.series_id is None
