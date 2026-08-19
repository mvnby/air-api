from httpx import ASGITransport, AsyncClient
import pytest

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope
from main import app
from models import Product, Tag, TagGroup
from models.tenancy import TenantScope
from services.feature_resolver_service import FeatureResolverService
from services.public_catalog_service import PublicCatalogService, PublicProductPage
from services.public_catalog_visibility_service import PublicProductProjection
from services.public_catalog_disclosure import CANONICAL_PUBLIC_DISCLOSURE
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


def _attach_mixed_taxonomy(product: Product) -> None:
    public_group = TagGroup(
        id=10,
        title="Public",
        slug="public",
        is_public=True,
    )
    hidden_group = TagGroup(
        id=11,
        title="Internal group",
        slug="internal-group",
        is_public=False,
    )
    public_tag = Tag(
        id=20,
        group_id=10,
        title="Visible tag",
        slug="visible-tag",
        is_public=True,
    )
    hidden_tag = Tag(
        id=21,
        group_id=10,
        title="Internal tag",
        slug="internal-tag",
        is_public=False,
    )
    hidden_group_tag = Tag(
        id=22,
        group_id=11,
        title="Internal group tag",
        slug="internal-group-tag",
        is_public=True,
    )
    public_tag.group = public_group
    hidden_tag.group = public_group
    hidden_group_tag.group = hidden_group
    product.tags = [public_tag, hidden_tag, hidden_group_tag]


@pytest.mark.asyncio
async def test_public_catalog_includes_city_availability(monkeypatch):
    product = _make_product()
    _attach_mixed_taxonomy(product)

    async def override_get_session():
        yield object()

    async def override_tenant_scope():
        return TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
            is_canonical_storefront=True,
        )

    async def fake_get_catalog_page(*args, **kwargs):
        return {
            "items": [
                PublicProductProjection(
                    product=product,
                    price=product.price,
                    old_price=product.old_price,
                    disclosure_policy=CANONICAL_PUBLIC_DISCLOSURE,
                )
            ],
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

    monkeypatch.setattr(PublicCatalogService, "get_catalog_page", fake_get_catalog_page)
    monkeypatch.setattr(ProductService, "get_supply_metrics_map", fake_get_supply_metrics_map)
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", fake_resolve_features)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_public_tenant_scope] = override_tenant_scope

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
    assert [tag["slug"] for tag in payload["items"][0]["tags"]] == [
        "visible-tag"
    ]


@pytest.mark.asyncio
async def test_public_product_detail_includes_city_availability(monkeypatch):
    product = _make_product(34)
    _attach_mixed_taxonomy(product)

    async def override_get_session():
        yield object()

    async def override_tenant_scope():
        return TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
            is_canonical_storefront=True,
        )

    async def fake_get_product_page(*args, **kwargs):
        return PublicProductPage(
            product=PublicProductProjection(
                product=product,
                price=product.price,
                old_price=product.old_price,
                disclosure_policy=CANONICAL_PUBLIC_DISCLOSURE,
            ),
            siblings=[],
        )

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

    monkeypatch.setattr(PublicCatalogService, "get_product_page", fake_get_product_page)
    monkeypatch.setattr(ProductService, "get_supply_metrics_map", fake_get_supply_metrics_map)
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", fake_resolve_features)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_public_tenant_scope] = override_tenant_scope

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
    assert [tag["slug"] for tag in payload["tags"]] == ["visible-tag"]
