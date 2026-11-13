"""Keep public pricing and availability on one bounded supply calculation."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from crud.installation_discount import InstallationDiscountDAO
from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from models import Brand, GlobalConfig, InstallationDiscountPolicy, Product, ProductSeries
from models.supplier import (
    ProductLocalStock,
    ProductSupplierMapping,
    Supplier,
    SupplierOffer,
    SupplierPriceSource,
)
from models.tenancy import TenantScope
from routers import api_products
from services.catalog import CatalogService
from services.catalog_document_service import CatalogDocumentService
from services.feature_resolver_service import FeatureResolverService
from services.fx_rate_service import FxRateService
from services.installation_discount_service import InstallationDiscountService
from services.product_read_service import ProductReadService
from services.product_series_service import ProductSeriesService
from services.product_supply_metrics_service import ProductSupplyMetricsService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services import public_series_page_service
from services.public_series_page_service import PublicSeriesPageService
from services.warranty_policy_resolver import WarrantyPolicyResolver


@pytest.fixture
async def supply_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("currency", "wholesale", "active", "expected_queries", "expected_cost"),
    [
        (None, None, True, 2, None),
        ("BYN", 1500, True, 4, 1500.0),
        ("USD", 500, True, 7, 1600.0),
        ("usd", 500, True, 7, 1600.0),
        ("USD", None, True, 4, None),
        ("USD", 500, False, 4, None),
    ],
)
async def test_metrics_only_resolve_fx_for_active_priced_usd_offers(
    supply_session, monkeypatch, currency, wholesale, active, expected_queries, expected_cost,
):
    session = supply_session
    product = Product(title="AC", slug="query-budget-ac", price=2500)
    supplier = Supplier(name="Relevant supplier", code="relevant")
    unrelated = Supplier(name="Unrelated supplier", code="unrelated")
    session.add_all([
        product, supplier, unrelated,
        GlobalConfig(key="fx_rate_source", value=(
            "manual" if currency and currency.upper() == "USD" and wholesale is not None and active else "nbrb"
        )),
        GlobalConfig(key="fx_rate_usd_byn", value="3.2"),
        GlobalConfig(key="fx_supplier_markup_percent", value="0"),
    ])
    await session.flush()
    session.add(ProductLocalStock(product_id=product.id, qty=2))
    session.add(SupplierPriceSource(supplier_id=unrelated.id, city_bucket="vitebsk"))
    if currency is not None:
        session.add_all([
            SupplierPriceSource(supplier_id=supplier.id, city_bucket="minsk"),
            ProductSupplierMapping(product_id=product.id, supplier_id=supplier.id, external_id="sku"),
            SupplierOffer(
                supplier_id=supplier.id, external_id="sku", qty=4,
                wholesale_value=wholesale, wholesale_currency=currency, is_active=active,
            ),
        ])
    await session.commit()

    calls = []

    def record_sql(connection, cursor, statement, parameters, context, executemany):
        calls.append((statement, parameters))

    network = AsyncMock(side_effect=AssertionError("Manual/local/BYN pricing must not use HTTP"))
    monkeypatch.setattr(FxRateService, "_fetch_nbrb_rates", network)
    event.listen(session.bind.sync_engine, "before_cursor_execute", record_sql)
    try:
        metrics = await ProductSupplyMetricsService.compute_for_products(session, [product])
    finally:
        event.remove(session.bind.sync_engine, "before_cursor_execute", record_sql)

    assert len(calls) == expected_queries
    assert metrics[product.id]["min_cost_byn"] == expected_cost
    assert metrics[product.id]["vitebsk_qty"] == 2
    assert metrics[product.id]["minsk_qty"] == (4 if currency and active else 0)
    assert metrics[product.id]["availability_status"] == "in_stock_now"
    assert metrics[product.id]["margin_abs_preview"] == (
        2500 - expected_cost if expected_cost is not None else None
    )
    network.assert_not_awaited()
    source_queries = [(sql, params) for sql, params in calls if "FROM supplier_price_source" in sql]
    if currency is not None:
        assert len(source_queries) == 1
        assert "supplier_price_source.supplier_id IN" in source_queries[0][0]
        assert source_queries[0][1] == (supplier.id,)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    ("endpoint", "canonical"),
    [("catalog", True), ("catalog", False), ("detail", True), ("detail", False),
     ("featured", True), ("series", True), ("series", False)],
)
async def test_public_discount_and_response_share_one_supply_calculation(
    monkeypatch, endpoint, canonical, enabled,
):
    product = Product(id=1, title="AC", slug="single-supply-ac", price=2500, is_published=True)
    effective_price = 2500 if canonical else 1800
    scope = TenantScope(tenant_id=1 if canonical else 2, storefront_id=1 if canonical else 2,
                        is_canonical_storefront=canonical)
    metrics = AsyncMock(return_value={1: {
        "min_cost_byn": 1600, "vitebsk_qty": 0, "minsk_qty": 4,
        "availability_status": "available_2_3_days",
    }})
    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", metrics)
    monkeypatch.setattr(InstallationDiscountDAO, "get_policy", AsyncMock(return_value=InstallationDiscountPolicy(
        id=1, is_enabled=enabled, default_discount=100, minimum_margin=350,
    )))
    monkeypatch.setattr(InstallationDiscountDAO, "get_rules_by_product_ids", AsyncMock(return_value={}))
    monkeypatch.setattr(InstallationDiscountDAO, "get_legacy_default_discount", AsyncMock(return_value="75"))
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", AsyncMock(return_value={}))
    monkeypatch.setattr(api_products, "enrich_public_products", AsyncMock())
    monkeypatch.setattr(WarrantyPolicyResolver, "resolve_public", AsyncMock(return_value={}))

    session = object()
    if endpoint == "catalog":
        monkeypatch.setattr(ProductReadService, "get_catalog_page", AsyncMock(return_value={
            "items": [product], "meta": {"total": 1, "page": 1, "limit": 20, "pages": 1},
        }))
        monkeypatch.setattr(PublicCatalogDAO, "get_filtered", AsyncMock(return_value=[(product, effective_price, None)]))
        monkeypatch.setattr(PublicCatalogDAO, "count_filtered", AsyncMock(return_value=1))
        response = await api_products.get_catalog(
            session=session, tenant_scope=scope, tag_slugs=None, brand_slugs=None,
            color=None, indoor_types=None, q=None,
        )
        item = response.items[0]
    elif endpoint == "detail":
        monkeypatch.setattr(ProductReadService, "get_public_product_by_identifier", AsyncMock(return_value=product))
        monkeypatch.setattr(ProductSeriesService, "get_series_siblings", AsyncMock(return_value=[]))
        monkeypatch.setattr(PublicCatalogDAO, "get_by_identifier", AsyncMock(return_value=(product, effective_price, None)))
        monkeypatch.setattr(PublicCatalogDAO, "get_series_siblings", AsyncMock(return_value=[]))
        item = await api_products.get_product_by_identifier(product.slug, session=session, tenant_scope=scope)
    elif endpoint == "featured":
        monkeypatch.setattr(CatalogService, "get_vitebsk_featured_products", AsyncMock(return_value=[product]))
        item = (await api_products.get_vitebsk_featured_products(session=session, tenant_scope=scope))[0]
    else:
        from types import SimpleNamespace

        brand = Brand(id=1, title="Brand", slug="brand", is_published=True)
        series = ProductSeries(id=1, brand_id=1, title="Series", slug="series", is_published=True)
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: (series, brand))))
        monkeypatch.setattr(ProductDAO, "get_published_by_series_id", AsyncMock(return_value=[product]))
        monkeypatch.setattr(PublicCatalogDAO, "get_by_series_id", AsyncMock(return_value=[(product, effective_price, None)]))
        monkeypatch.setattr(public_series_page_service, "enrich_public_products", AsyncMock())
        monkeypatch.setattr(CatalogDocumentService, "get_effective_documents", AsyncMock(return_value=[]))
        monkeypatch.setattr(PublicSeriesPageService, "_get_related_series", AsyncMock(return_value=[]))
        response = await PublicSeriesPageService.get_by_slugs(
            session, brand_slug=brand.slug, series_slug=series.slug, tenant_scope=scope,
        )
        item = response.products[0]

    metrics.assert_awaited_once_with(session, [product])
    assert item.price == effective_price
    expected_discount = (100 if canonical else 0) if enabled else 75
    assert item.installation_discount == expected_discount
    assert item.availability_status == "available_2_3_days"
    assert "supply_metrics" not in item.model_dump()
    assert "min_cost_byn" not in item.model_dump()


@pytest.mark.asyncio
async def test_explicit_empty_metrics_do_not_trigger_a_second_calculation(monkeypatch):
    product = Product(id=1, title="AC", slug="missing-cost-ac", price=2500)
    metrics = AsyncMock(side_effect=AssertionError("An explicitly supplied result must be reused"))
    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", metrics)
    monkeypatch.setattr(InstallationDiscountDAO, "get_policy", AsyncMock(return_value=InstallationDiscountPolicy(
        id=1, is_enabled=True, default_discount=100, minimum_margin=350,
    )))
    monkeypatch.setattr(InstallationDiscountDAO, "get_rules_by_product_ids", AsyncMock(return_value={}))

    decorated = await InstallationDiscountService.decorate_public_projections(
        object(), [PublicCatalogVisibilityService.project_product(product)], supply_metrics={},
    )

    metrics.assert_not_awaited()
    assert decorated[0].installation_discount == 0
    assert decorated[0].supply_metrics == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_detail_does_not_load_supply_or_fx_for_usd_sibling(
    supply_session, monkeypatch, canonical, enabled,
):
    session = supply_session
    product = Product(
        title="Local AC", slug="local-detail-ac", price=2500, is_published=True,
        tags=[], gallery_images=[], attachments=[],
    )
    sibling = Product(
        title="USD sibling", slug="usd-sibling", price=3000, is_published=True,
        tags=[], gallery_images=[], attachments=[],
    )
    supplier = Supplier(name="USD supplier", code="usd-sibling")
    session.add_all([
        product, sibling, supplier,
        InstallationDiscountPolicy(id=1, is_enabled=enabled, default_discount=100, minimum_margin=350),
        GlobalConfig(key="install_discount", value="75"),
        GlobalConfig(key="fx_rate_source", value="nbrb"),
    ])
    await session.flush()
    session.add_all([
        ProductLocalStock(product_id=product.id, qty=2),
        SupplierPriceSource(supplier_id=supplier.id),
        ProductSupplierMapping(product_id=sibling.id, supplier_id=supplier.id, external_id="usd-sibling"),
        SupplierOffer(
            supplier_id=supplier.id, external_id="usd-sibling", qty=4,
            wholesale_currency="USD", wholesale_value=500,
        ),
    ])
    await session.commit()
    sibling_price = 3000 if canonical else 2900
    scope = TenantScope(tenant_id=1, storefront_id=1, is_canonical_storefront=canonical)
    metrics = AsyncMock(wraps=ProductSupplyMetricsService.compute_for_products)
    fx = AsyncMock(side_effect=AssertionError("Sibling-only USD cost must not trigger FX"))
    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", metrics)
    monkeypatch.setattr(FxRateService, "get_supplier_usd_byn_rate", fx)
    monkeypatch.setattr(ProductReadService, "get_public_product_by_identifier", AsyncMock(return_value=product))
    monkeypatch.setattr(ProductSeriesService, "get_series_siblings", AsyncMock(return_value=[sibling]))
    monkeypatch.setattr(PublicCatalogDAO, "get_by_identifier", AsyncMock(return_value=(product, 2400, None)))
    monkeypatch.setattr(PublicCatalogDAO, "get_series_siblings", AsyncMock(return_value=[(sibling, sibling_price, None)]))
    monkeypatch.setattr(FeatureResolverService, "resolve_for_products", AsyncMock(return_value={}))
    monkeypatch.setattr(api_products, "enrich_public_products", AsyncMock())
    monkeypatch.setattr(WarrantyPolicyResolver, "resolve_public", AsyncMock(return_value={}))

    item = await api_products.get_product_by_identifier(product.slug, session=session, tenant_scope=scope)

    metrics.assert_awaited_once_with(session, [product])
    fx.assert_not_awaited()
    assert item.installation_discount == (0 if enabled else 75)
    assert item.vitebsk_qty == (2 if canonical else 0)
    assert [(candidate.id, candidate.price) for candidate in item.series_siblings] == [(sibling.id, sibling_price)]
