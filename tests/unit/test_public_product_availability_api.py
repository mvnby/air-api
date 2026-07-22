from httpx import ASGITransport, AsyncClient
import pytest

from core.database import get_session
from main import app
from models import Product
from services.feature_resolver_service import FeatureResolverService
from services.product_service import ProductService


def _make_product(product_id: int = 1) -> Product:
    return Product(
        id=product_id,
        title="Test AC",
        slug=f"test-ac-{product_id}",
        description="Demo",
        price=2500,
        old_price=2700,
        specs={"area_m2": 25},
        is_inverter=True,
        is_published=True,
    )


@pytest.mark.asyncio
async def test_public_catalog_includes_city_availability(monkeypatch):
    product = _make_product()

    async def override_get_session():
        yield object()

    async def fake_get_catalog_page(*args, **kwargs):
        return {
            "items": [product],
            "meta": {"total": 1, "page": 1, "limit": 20, "pages": 1},
        }

    async def fake_get_supply_metrics_map(*args, **kwargs):
        return {
            product.id: {
                "vitebsk_qty": 0,
                "minsk_qty": 3,
                "availability_status": "available_2_3_days",
            }
        }

    async def fake_resolve_features(*args, **kwargs):
        return {}

    monkeypatch.setattr(ProductService, "get_catalog_page", fake_get_catalog_page)
    monkeypatch.setattr(ProductService, "get_supply_metrics_map", fake_get_supply_metrics_map)
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", fake_resolve_features)
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["vitebsk_qty"] == 0
    assert payload["items"][0]["minsk_qty"] == 3
    assert payload["items"][0]["availability_status"] == "available_2_3_days"


@pytest.mark.asyncio
async def test_public_product_detail_includes_city_availability(monkeypatch):
    product = _make_product(34)

    async def override_get_session():
        yield object()

    async def fake_get_public_product_by_identifier(*args, **kwargs):
        return product

    async def fake_get_series_siblings(*args, **kwargs):
        return []

    async def fake_get_supply_metrics_map(*args, **kwargs):
        return {
            product.id: {
                "vitebsk_qty": 0,
                "minsk_qty": 0,
                "availability_status": "check_availability",
            }
        }

    async def fake_resolve_features(*args, **kwargs):
        return {}

    monkeypatch.setattr(ProductService, "get_public_product_by_identifier", fake_get_public_product_by_identifier)
    monkeypatch.setattr(ProductService, "get_series_siblings", fake_get_series_siblings)
    monkeypatch.setattr(ProductService, "get_supply_metrics_map", fake_get_supply_metrics_map)
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", fake_resolve_features)
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/products/{product.slug}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["vitebsk_qty"] == 0
    assert payload["minsk_qty"] == 0
    assert payload["availability_status"] == "check_availability"
