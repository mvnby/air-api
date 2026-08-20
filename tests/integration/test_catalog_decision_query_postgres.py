import pytest
from sqlmodel import select

from models import Product, ProductTagLink, Tag, TagGroup
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import TenantScope
from services.catalog_decision_projection import (
    CatalogDecisionFilters,
    CatalogDecisionQueryService,
    CatalogDecisionScopeError,
)


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
