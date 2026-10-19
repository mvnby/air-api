from unittest.mock import AsyncMock

import pytest

from models import Product
from models.catalog_accessory import ProductAccessoryOverride, SeriesAccessoryLink
from models.tenancy import TenantScope
from services.catalog_accessory_service import CatalogAccessoryService
from services.product_read_service import ProductReadService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO


@pytest.mark.asyncio
@pytest.mark.parametrize("specs,suggested", [
    ({"wifi_state": "ready"}, True),
    ({"wifi_state": "builtin"}, False),
    ({"wifi_state": "none"}, False),
    ({}, False),
    ({"__typed_specs": {"wifi_state": {"value": "ready"}}}, True),
])
async def test_catalog_accessories_wifi_ready_suggests_purchase_but_builtin_never_does(monkeypatch, specs, suggested):
    parent = Product(id=1, title="Air Conditioner", slug="air", price=1000, series_id=5, specs=specs)
    accessory = Product(id=2, title="Wi-Fi Module", slug="wifi", price=80, old_price=99, product_kind="accessory", specs={"accessory_type": "wifi_module"})
    links = [SeriesAccessoryLink(series_id=5, accessory_product_id=2, sort_order=0)]
    monkeypatch.setattr(CatalogAccessoryService, "_links", AsyncMock(return_value=(links, [])))
    monkeypatch.setattr(PublicCatalogVisibilityService, "is_canonical_scope", AsyncMock(return_value=True))
    monkeypatch.setattr(ProductDAO, "get_by_ids", AsyncMock(return_value=[accessory]))
    monkeypatch.setattr(ProductReadService, "get_supply_metrics_map", AsyncMock(return_value={2: {"availability_status": "in_stock_now"}}))
    result = await CatalogAccessoryService.resolve_public(object(), [parent], tenant_scope=TenantScope(tenant_id=1, storefront_id=1))
    card = result[1][0]
    assert card.suggested_for_purchase is suggested
    assert card.price == 80
    assert card.old_price == 99
    assert card.availability_status == "in_stock_now"
    assert parent.specs == specs


@pytest.mark.asyncio
async def test_catalog_accessories_partner_uses_offer_price_and_batch_boundary(monkeypatch):
    parents = [Product(id=i, title=f"Model {i}", slug=f"model-{i}", price=1000, series_id=5) for i in (1, 3)]
    visible = Product(id=2, title="Module", slug="module", price=80, product_kind="accessory")
    links = [SeriesAccessoryLink(series_id=5, accessory_product_id=2), SeriesAccessoryLink(series_id=5, accessory_product_id=4, sort_order=1)]
    overrides = [ProductAccessoryOverride(product_id=3, accessory_product_id=2, is_enabled=False)]
    monkeypatch.setattr(CatalogAccessoryService, "_links", AsyncMock(return_value=(links, overrides)))
    monkeypatch.setattr(PublicCatalogVisibilityService, "is_canonical_scope", AsyncMock(return_value=False))
    shared_read = AsyncMock()
    scoped_read = AsyncMock(return_value=[(visible, 250, 300)])
    metrics = AsyncMock(return_value={2: {"availability_status": "in_stock_now", "vitebsk_qty": 17, "min_cost_byn": 8}})
    monkeypatch.setattr(ProductDAO, "get_by_ids", shared_read)
    monkeypatch.setattr(PublicCatalogDAO, "get_by_ids", scoped_read)
    monkeypatch.setattr(ProductReadService, "get_supply_metrics_map", metrics)
    scope = TenantScope(tenant_id=8, storefront_id=9)
    result = await CatalogAccessoryService.resolve_public(object(), parents, tenant_scope=scope)
    assert [card.product_id for card in result[1]] == [2]
    assert result[3] == []
    assert (result[1][0].price, result[1][0].old_price) == (250, 300)
    assert {"vitebsk_qty", "minsk_qty", "min_cost_byn", "source_url"}.isdisjoint(result[1][0].model_dump())
    shared_read.assert_not_awaited()
    scoped_read.assert_awaited_once()
    assert scoped_read.await_args.kwargs["tenant_scope"] is scope
    assert scoped_read.await_args.kwargs["product_ids"] == [2, 4]
    assert scoped_read.await_args.kwargs["require_catalog_grant"] is True
    metrics.assert_awaited_once()
