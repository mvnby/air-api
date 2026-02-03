import pytest
from httpx import AsyncClient
from models import Product

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
