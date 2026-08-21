import pytest
from sqlalchemy import event
from sqlmodel import select

from models import Brand, Order, Product, ProductSeries, ProductTagLink, Tag, TagGroup
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import TenantScope
from services.catalog_decision_projection import (
    CatalogDecisionFilters,
    CatalogDecisionQueryService,
    CatalogDecisionScopeError,
)
from services.catalog_decision_quick_order_service import CatalogDecisionQuickOrderService


async def _category(session, slug: str) -> Tag:
    group = TagGroup(title="Decision category", slug="decision-category", is_public=True)
    session.add(group)
    await session.flush()
    tag = Tag(title=slug, slug=slug, group_id=group.id, is_public=True)
    session.add(tag)
    await session.flush()
    return tag


@pytest.mark.asyncio
async def test_catalog_decision_sorts_commercial_metrics_before_pagination_and_keeps_nulls_last(db):
    supplier = Supplier(name="Decision Supplier", code="decision-supplier", is_active=True)
    db.add(supplier)
    await db.flush()
    products = [
        Product(title="DECISION expensive cost", slug="decision-cost-high", price=1000, power_cooling=3.5, specs={"area_m2": 35, "wifi_ready": True, "__filter_indoor_type": "wall"}),
        Product(title="DECISION cheap cost", slug="decision-cost-low", price=1000, power_cooling=3.5, specs={"area_m2": 35, "wifi_ready": "ready", "__filter_indoor_type": "cassette"}),
        Product(title="DECISION no offer", slug="decision-no-offer", price=1000, power_cooling=3.5, specs={"area_m2": 35, "wifi_ready": False, "__filter_indoor_type": "duct"}),
    ]
    db.add_all(products)
    await db.flush()
    db.add_all([
        SupplierOffer(supplier_id=supplier.id, external_id="HIGH", wholesale_value=700, wholesale_currency="BYN", rrc_byn=1100, qty=3),
        SupplierOffer(supplier_id=supplier.id, external_id="LOW", wholesale_value=400, wholesale_currency="BYN", rrc_byn=950, qty=1),
        ProductSupplierMapping(product_id=products[0].id, supplier_id=supplier.id, external_id="HIGH"),
        ProductSupplierMapping(product_id=products[1].id, supplier_id=supplier.id, external_id="LOW"),
    ])
    await db.commit()
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    first = await CatalogDecisionQueryService.list_system_products(db, tenant_scope=scope, filters=CatalogDecisionFilters(search="DECISION"), page=1, limit=1, sort="purchase_cost", direction="asc")
    second = await CatalogDecisionQueryService.list_system_products(db, tenant_scope=scope, filters=CatalogDecisionFilters(search="DECISION"), page=2, limit=1, sort="purchase_cost", direction="asc")
    third = await CatalogDecisionQueryService.list_system_products(db, tenant_scope=scope, filters=CatalogDecisionFilters(search="DECISION"), page=3, limit=1, sort="purchase_cost", direction="asc")
    assert [first["items"][0]["id"], second["items"][0]["id"], third["items"][0]["id"]] == [products[1].id, products[0].id, products[2].id]
    assert first["items"][0]["margin_abs_byn"] == 600
    assert third["items"][0]["purchase_cost_byn"] is None


@pytest.mark.asyncio
async def test_catalog_decision_filters_use_normalized_power_and_form_factor(db):
    wall = Product(title="DECISION wall", slug="decision-wall", price=1000, power_cooling=3.5, specs={"area_m2": 35, "capacity_cooling_min_kw": "3.2", "capacity_cooling_max_kw": "3.8", "__filter_indoor_type": "wall"})
    cassette = Product(title="DECISION cassette", slug="decision-cassette", price=1000, power_cooling=5.0, specs={"area_m2": 55, "capacity_cooling_min_kw": "4.5", "capacity_cooling_max_kw": "5.5", "__filter_indoor_type": "cassette"})
    db.add_all([wall, cassette])
    await db.commit()
    result = await CatalogDecisionQueryService.list_system_products(db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True), filters=CatalogDecisionFilters(search="DECISION", cooling_min_kw=3.2, cooling_max_kw=3.8, indoor_form_factor="wall", area_max=40), page=1, limit=20, sort="title", direction="asc")
    assert [item["id"] for item in result["items"]] == [wall.id]


@pytest.mark.asyncio
async def test_catalog_decision_rejects_tenant_scope_before_query(db):
    with pytest.raises(CatalogDecisionScopeError):
        await CatalogDecisionQueryService.list_system_products(db, tenant_scope=TenantScope(tenant_id=99, storefront_id=99, is_system=False), filters=CatalogDecisionFilters(), page=1, limit=10, sort="title", direction="asc")

    with pytest.raises(CatalogDecisionScopeError):
        await CatalogDecisionQueryService.get_system_product_snapshots(
            db,
            tenant_scope=TenantScope(tenant_id=99, storefront_id=99, is_system=False),
            product_ids=[1],
        )


@pytest.mark.asyncio
async def test_catalog_decision_projection_has_a_bounded_query_count(db):
    """The number of rows must not turn supplier metrics into N+1 queries."""
    statements: list[str] = []

    def collect(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    engine = db.bind
    assert engine is not None
    event.listen(engine.sync_engine, "after_cursor_execute", collect)
    try:
        await CatalogDecisionQueryService.list_system_products(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            filters=CatalogDecisionFilters(),
            page=1,
            limit=100,
            sort="purchase_cost",
            direction="asc",
        )
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", collect)

    # Cold FX configuration needs at most three reads; count + page query add two.
    assert len(statements) <= 5


@pytest.mark.asyncio
async def test_catalog_decision_order_snapshots_are_batched(db):
    products = [
        Product(title=f"DECISION snapshot {index}", slug=f"decision-snapshot-{index}", price=1000 + index)
        for index in range(8)
    ]
    db.add_all(products)
    await db.commit()
    statements: list[str] = []

    def collect(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    engine = db.bind
    assert engine is not None
    event.listen(engine.sync_engine, "after_cursor_execute", collect)
    try:
        snapshots = await CatalogDecisionQueryService.get_system_product_snapshots(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            product_ids=[int(product.id) for product in products],
        )
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", collect)

    assert set(snapshots) == {int(product.id) for product in products}
    # Cold FX configuration needs at most three reads; all product metrics use one query.
    assert len(statements) <= 4


@pytest.mark.asyncio
async def test_catalog_decision_quick_order_is_anonymous_atomic_and_idempotent(db):
    products = [
        Product(title="DECISION quick 12", slug="decision-quick-12", price=2200),
        Product(title="DECISION quick 18", slug="decision-quick-18", price=3100),
    ]
    db.add_all(products)
    await db.commit()
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    ids = [int(product.id) for product in products]

    first = await CatalogDecisionQuickOrderService.create(
        db,
        product_ids=ids,
        idempotency_key="quick-order-retry-1",
        prospect_type="company",
        tenant_scope=scope,
    )
    retry = await CatalogDecisionQuickOrderService.create(
        db,
        product_ids=list(reversed(ids)),
        idempotency_key="quick-order-retry-1",
        prospect_type="individual",
        tenant_scope=scope,
    )

    assert retry["id"] == first["id"]
    assert first["customer"] is None
    assert first["status"] == "negotiation"
    assert len(first["proposals"]) == 1
    assert first["proposals"][0]["is_selected"] is True
    assert {line["product_id"] for line in first["proposals"][0]["product_lines"]} == set(ids)
    order = await db.get(Order, first["id"])
    assert order is not None
    assert order.technical_meta["customer_state"] == "unidentified"
    assert order.technical_meta["prospect_type"] == "company"
    assert len((await db.execute(select(Order).where(Order.source_fingerprint == order.source_fingerprint))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_catalog_decision_quick_order_rolls_back_when_any_product_is_missing(db):
    product = Product(title="DECISION rollback", slug="decision-quick-rollback", price=1500)
    db.add(product)
    await db.commit()
    before = len((await db.execute(select(Order))).scalars().all())

    with pytest.raises(ValueError, match="Товары не найдены"):
        await CatalogDecisionQuickOrderService.create(
            db,
            product_ids=[int(product.id), 987654321],
            idempotency_key="quick-order-rollback-1",
            prospect_type="individual",
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        )

    assert len((await db.execute(select(Order))).scalars().all()) == before


@pytest.mark.asyncio
async def test_catalog_decision_quick_order_rejects_tenant_projection_before_creating_order(db):
    before = len((await db.execute(select(Order))).scalars().all())
    with pytest.raises(CatalogDecisionScopeError):
        await CatalogDecisionQuickOrderService.create(
            db,
            product_ids=[1],
            idempotency_key="tenant-quick-order-blocked",
            prospect_type="individual",
            tenant_scope=TenantScope(tenant_id=99, storefront_id=99, is_system=False),
        )
    assert len((await db.execute(select(Order))).scalars().all()) == before


@pytest.mark.asyncio
async def test_catalog_decision_ignores_legacy_unit_suffixes_without_failing_the_page(db):
    """A malformed historical spec must become NULL, never a 500 for every manager."""
    legacy = Product(
        title="DECISION legacy suffix", slug="decision-legacy-suffix", price=1000,
        specs={"capacity_cooling_kw": "0.88 кВт", "capacity_cooling_min_kw": "0.88 кВт", "area_m2": "35"},
    )
    canonical = Product(
        title="DECISION canonical numeric", slug="decision-canonical-numeric", price=1000,
        specs={"capacity_cooling_kw": "3.5", "capacity_cooling_min_kw": "3.2", "capacity_cooling_max_kw": "3.8", "area_m2": "35"},
    )
    db.add_all([legacy, canonical])
    await db.commit()

    result = await CatalogDecisionQueryService.list_system_products(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        filters=CatalogDecisionFilters(search="DECISION"), page=1, limit=20, sort="title", direction="asc",
    )

    by_id = {item["id"]: item for item in result["items"]}
    assert set(by_id) == {legacy.id, canonical.id}
    assert by_id[legacy.id]["cooling_power_kw"] is None
    assert by_id[canonical.id]["cooling_power_kw"] == 3.5


@pytest.mark.asyncio
async def test_catalog_decision_smart_search_and_multiple_btu_classes(db):
    brand = Brand(title="Decision Gree", slug="decision-gree")
    db.add(brand)
    await db.flush()
    series = ProductSeries(title="Decision Elite", slug="decision-elite", brand_id=brand.id)
    db.add(series)
    await db.flush()
    nine = Product(title="DECISION indoor 09", slug="decision-09", price=900, brand_id=brand.id, series_id=series.id, power_cooling=2.6, specs={"area_m2": 28})
    twelve = Product(title="DECISION indoor 12", slug="decision-12", price=1000, brand_id=brand.id, series_id=series.id, power_cooling=3.5, specs={"area_m2": 35})
    db.add_all([nine, twelve])
    await db.commit()

    result = await CatalogDecisionQueryService.list_system_products(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        filters=CatalogDecisionFilters(search="Gree 12", cooling_btu_classes=(9, 12)), page=1, limit=20, sort="title", direction="asc",
    )

    # Text and nominal tokens are ANDed, exactly as in the public smart search.
    assert [item["id"] for item in result["items"]] == [twelve.id]


@pytest.mark.asyncio
async def test_catalog_decision_filter_options_keep_series_owner(db):
    brand = Brand(title="Decision option brand", slug="decision-option-brand")
    db.add(brand)
    await db.flush()
    series = ProductSeries(title="Decision shared-name", slug="decision-shared-name", brand_id=brand.id)
    db.add(series)
    await db.flush()
    db.add(Product(title="DECISION option product", slug="decision-option-product", price=1000, brand_id=brand.id, series_id=series.id))
    await db.commit()

    options = await CatalogDecisionQueryService.list_system_filter_options(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
    )

    assert {item["id"]: item["brand_id"] for item in options["series"]}[series.id] == brand.id
