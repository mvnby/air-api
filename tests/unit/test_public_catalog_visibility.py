from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from crud.canonical_public_catalog import CanonicalPublicCatalogDAO
from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from models import Product
from models.tenancy import TenantScope
from services.product_read_service import ProductReadService
from services.public_catalog_service import PublicCatalogService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _product(product_id: int = 17) -> Product:
    return Product(
        id=product_id,
        title="Scoped product",
        slug=f"scoped-product-{product_id}",
        price=9000,
        old_price=9500,
        specs={"area_m2": 25},
        is_published=True,
    )


class _RowsResult:
    def all(self):
        return []


class _CapturingSession:
    bind = None

    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _RowsResult()


def test_secondary_catalog_sql_requires_exact_active_published_offer_pair():
    scope_a = TenantScope(
        tenant_id=7,
        storefront_id=11,
        is_canonical_storefront=False,
    )
    scope_b = TenantScope(
        tenant_id=8,
        storefront_id=12,
        is_canonical_storefront=False,
    )

    sql_a = _postgres_sql(PublicCatalogDAO._select_products(scope_a))
    sql_b = _postgres_sql(PublicCatalogDAO._select_products(scope_b))

    assert "product.is_published IS true" in sql_a
    assert "tenant_offer.tenant_id = 7" in sql_a
    assert "tenant_offer.storefront_id = 11" in sql_a
    assert "tenant_offer.status = 'active'" in sql_a
    assert "tenant_offer.is_published IS true" in sql_a
    assert "tenant_offer.tenant_id = 8" in sql_b
    assert "tenant_offer.storefront_id = 12" in sql_b
    assert sql_a != sql_b


@pytest.mark.asyncio
async def test_secondary_price_filter_sort_and_pagination_use_offer_column():
    session = _CapturingSession()

    rows = await PublicCatalogDAO.get_filtered(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=False,
        ),
        min_price=2500,
        max_price=3500,
        sort="price_asc",
        page=2,
        limit=20,
    )

    sql = _postgres_sql(session.statement)
    assert rows == []
    assert "tenant_offer.price >= 2500" in sql
    assert "tenant_offer.price <= 3500" in sql
    assert "ORDER BY tenant_offer.price ASC, product.id ASC" in sql
    assert "LIMIT 20 OFFSET 20" in sql
    assert "product.price >=" not in sql
    assert "product.price <=" not in sql


@pytest.mark.asyncio
async def test_secondary_q_only_searches_public_taxonomy():
    session = _CapturingSession()

    rows = await PublicCatalogDAO.get_filtered(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=False,
        ),
        search_query="InternalTaxonomyTitle",
    )

    sql = _postgres_sql(session.statement)
    assert rows == []
    assert "tenant_offer.tenant_id = 7" in sql
    assert "tag.title ILIKE '%%InternalTaxonomyTitle%%'" in sql
    assert "tag.is_public IS true" in sql
    assert "tag_group.is_public IS true" in sql


@pytest.mark.asyncio
async def test_visibility_is_negative_across_storefront_a_and_b(monkeypatch):
    product = _product()
    scope_a = TenantScope(tenant_id=2, storefront_id=20, is_canonical_storefront=False)
    scope_b = TenantScope(tenant_id=2, storefront_id=21, is_canonical_storefront=False)
    seen_scopes: list[tuple[int, int]] = []

    async def fake_get_by_ids(
        _session,
        *,
        tenant_scope,
        product_ids,
        load_image_variants=False,
    ):
        assert product_ids == [17]
        assert load_image_variants is False
        pair = (tenant_scope.tenant_id, tenant_scope.storefront_id)
        seen_scopes.append(pair)
        return [(product, 3000, 3500)] if pair == (2, 20) else []

    monkeypatch.setattr(PublicCatalogDAO, "get_by_ids", fake_get_by_ids)

    visible_a = await PublicCatalogVisibilityService.get_visible_product_by_id(
        object(),
        tenant_scope=scope_a,
        product_id=17,
    )
    hidden_b = await PublicCatalogVisibilityService.get_visible_product_by_id(
        object(),
        tenant_scope=scope_b,
        product_id=17,
    )

    assert visible_a is not None
    assert visible_a.product is product
    assert visible_a.pricing == (3000, 3500)
    assert hidden_b is None
    assert seen_scopes == [(2, 20), (2, 21)]


@pytest.mark.asyncio
async def test_canonical_visibility_requires_published_product(monkeypatch):
    product = _product()
    captured = {}

    async def fake_get_by_id(_session, product_id, **kwargs):
        captured.update(product_id=product_id, **kwargs)
        return product

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)

    projection = await PublicCatalogVisibilityService.get_visible_product_by_id(
        object(),
        tenant_scope=TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
            is_canonical_storefront=True,
        ),
        product_id=17,
    )

    assert projection is not None
    assert projection.product is product
    assert captured == {"product_id": 17, "is_published": True}


@pytest.mark.asyncio
async def test_canonical_public_search_uses_canonical_public_dao(monkeypatch):
    captured = {}

    async def fake_get_filtered(_session, **kwargs):
        captured.update(kwargs)
        return []

    async def fake_metrics(_session, _products):
        return {}

    monkeypatch.setattr(CanonicalPublicCatalogDAO, "get_filtered", fake_get_filtered)
    monkeypatch.setattr(ProductReadService, "get_supply_metrics_map", fake_metrics)

    result = await PublicCatalogService.search(
        SimpleNamespace(),
        tenant_scope=TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
            is_canonical_storefront=True,
        ),
        query="hidden",
        is_inverter=None,
    )

    assert result == []
    assert captured["search_query"] == "hidden"
