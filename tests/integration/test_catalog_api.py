import pytest
from httpx import AsyncClient
from models import Product
from services.spec_normalizer import normalize_specs

@pytest.fixture
async def seed_product(db):
    """Seed a test product for catalog tests."""
    product = Product(
        title="Integration Test Product",
        slug="integration-test-product",
        price=1000,
        area=25,
        is_published=True
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@pytest.mark.asyncio
async def test_list_products(async_client: AsyncClient, seed_product):
    """Test fetching the product catalog."""
    response = await async_client.get("/api/v1/products")
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    
    # Verify seeded product is in the list
    slugs = [item["slug"] for item in data["items"]]
    assert seed_product.slug in slugs

@pytest.mark.asyncio
async def test_product_detail(async_client: AsyncClient, seed_product):
    """Test fetching a specific product by slug."""
    response = await async_client.get(f"/api/v1/products/{seed_product.slug}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seed_product.id
    assert data["title"] == seed_product.title
    assert data["slug"] == seed_product.slug

@pytest.mark.asyncio
async def test_product_not_found(async_client: AsyncClient):
    """Test fetching a non-existent product."""
    response = await async_client.get("/api/v1/products/non-existent-slug-12345")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_catalog_filters_by_wifi_and_heating(async_client: AsyncClient, db):
    good = Product(
        title="Good",
        slug="good",
        price=1000,
        area=35,
        is_inverter=True,
        is_published=True,
        specs=normalize_specs({"temp_range_heat": "от -25 до +24", "wifi_ready": "да"}),
    )
    weak = Product(
        title="Weak",
        slug="weak",
        price=1000,
        area=35,
        is_inverter=True,
        is_published=True,
        specs=normalize_specs({"temp_range_heat": "от -10 до +24", "wifi_ready": "нет"}),
    )
    db.add(good)
    db.add(weak)
    await db.commit()

    response = await async_client.get("/api/v1/products?has_wifi=true&heating_min=-20")
    assert response.status_code == 200
    payload = response.json()
    slugs = [item["slug"] for item in payload["items"]]
    assert "good" in slugs
    assert "weak" not in slugs
    assert all(not key.startswith("__") for key in payload["items"][0]["specs"].keys())
