from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import select

from core.config import settings
from models import (
    Brand, IntegrationOutboxEvent, OrderProductLink, Product, ProductLocalStock,
    ProductSeries, Storefront, Tenant, TenantCatalogGrant, TenantOffer,
)
from models.catalog_accessory import ProductAccessoryOverride, SeriesAccessoryLink
from models.tenancy import TenantScope
from schemas_catalog_accessories import ProductAccessoriesUpdate, SeriesAccessoriesUpdate
from services.catalog_accessory_service import CatalogAccessoryService
from services.catalog_revision_service import CatalogRevisionService


CANONICAL = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)


async def _seed(db):
    brand = Brand(title="Accessory Test", slug="accessory-test")
    db.add(brand)
    await db.flush()
    series = ProductSeries(title="FG", slug="fg-accessory-test", brand_id=brand.id)
    db.add(series)
    await db.flush()
    model = Product(title="FG Air Conditioner", slug="fg-air", price=1500, brand_id=brand.id, series_id=series.id, product_kind="complete_split_system", specs={"wifi_state": "ready"})
    unrelated = Product(title="Same Brand Other Series", slug="fg-unrelated", price=1200, brand_id=brand.id, product_kind="complete_split_system")
    accessories = [Product(title=f"Accessory Module {index}", slug=f"accessory-module-{index}", price=80 + index, old_price=100 + index, product_kind="accessory", specs={"accessory_type": "wifi_module"}) for index in range(3)]
    db.add_all([model, unrelated, *accessories])
    await db.commit()
    return series, model, unrelated, accessories


async def _state(db):
    revision = await CatalogRevisionService.get_current(db)
    events = list((await db.execute(select(IntegrationOutboxEvent.event_id))).scalars())
    return revision["revision"], set(events)


@pytest.mark.asyncio
async def test_catalog_accessories_inherit_exclude_include_and_reset_without_brand_or_wifi_inference(db):
    series, model, unrelated, accessories = await _seed(db)
    first, second, third = accessories
    await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=SeriesAccessoriesUpdate(accessory_product_ids=[second.id, first.id]))
    workspace = await CatalogAccessoryService.get_workspace(db, target_type="product", target_id=model.id)
    assert [item.accessory_product_id for item in workspace.items] == [second.id, first.id]
    assert all(item.inherited and item.override is None for item in workspace.items)
    await CatalogAccessoryService.set_product_accessories(db, product_id=model.id, payload=ProductAccessoriesUpdate(overrides=[
        {"accessory_product_id": first.id, "is_enabled": False},
        {"accessory_product_id": third.id, "is_enabled": True},
        {"accessory_product_id": second.id, "is_enabled": True},
    ]))
    resolved = await CatalogAccessoryService.resolve_public(db, [model, unrelated], tenant_scope=CANONICAL)
    assert [item.product_id for item in resolved[model.id]] == [second.id, third.id]
    assert resolved[unrelated.id] == []
    assert [item.compatibility_source for item in resolved[model.id]] == ["product", "product"]
    assert model.specs == {"wifi_state": "ready"}
    assert list((await db.execute(select(OrderProductLink))).scalars()) == []
    await CatalogAccessoryService.set_product_accessories(db, product_id=model.id, payload=ProductAccessoriesUpdate(overrides=[]))
    restored = await CatalogAccessoryService.resolve_public(db, [model], tenant_scope=CANONICAL)
    assert [item.product_id for item in restored[model.id]] == [second.id, first.id]
    assert all(item.compatibility_source == "series" for item in restored[model.id])


@pytest.mark.asyncio
async def test_catalog_accessories_semantic_noop_keeps_revision_and_stored_order(db):
    series, model, _, accessories = await _seed(db)
    payload = SeriesAccessoriesUpdate(accessory_product_ids=[accessories[1].id, accessories[0].id])
    before = await _state(db)
    await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=payload)
    after = await _state(db)
    assert after[0] == before[0] + 1
    assert len(after[1] - before[1]) == 1
    await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=payload)
    assert await _state(db) == after
    override = ProductAccessoriesUpdate(overrides=[{"accessory_product_id": accessories[0].id, "is_enabled": False}])
    await CatalogAccessoryService.set_product_accessories(db, product_id=model.id, payload=override)
    after_override = await _state(db)
    await CatalogAccessoryService.set_product_accessories(db, product_id=model.id, payload=override)
    assert await _state(db) == after_override
    rows = (await db.execute(select(SeriesAccessoryLink).order_by(SeriesAccessoryLink.sort_order))).scalars().all()
    assert [row.accessory_product_id for row in rows] == payload.accessory_product_ids


@pytest.mark.asyncio
async def test_catalog_accessories_validation_and_self_compatibility(db):
    series, model, unrelated, accessories = await _seed(db)
    before = await _state(db)
    for ids in ([model.id], [987654321]):
        with pytest.raises(HTTPException) as error:
            await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=SeriesAccessoriesUpdate(accessory_product_ids=ids))
        assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        await CatalogAccessoryService.set_product_accessories(db, product_id=accessories[0].id, payload=ProductAccessoriesUpdate(overrides=[{"accessory_product_id": accessories[0].id, "is_enabled": True}]))
    assert error.value.status_code == 400
    accessories[0].series_id = series.id
    db.add(accessories[0])
    await db.flush()
    with pytest.raises(HTTPException):
        await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=SeriesAccessoriesUpdate(accessory_product_ids=[accessories[0].id]))
    assert await _state(db) == before
    assert list((await db.execute(select(ProductAccessoryOverride))).scalars()) == []
    with pytest.raises(HTTPException) as error:
        await CatalogAccessoryService.get_workspace(db, target_type="series", target_id=987654321)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_catalog_accessories_public_price_stock_publication_and_tenant_offer_boundary(db):
    series, model, _, accessories = await _seed(db)
    available, no_offer, unpublished = accessories
    unpublished.is_published = False
    db.add(unpublished)
    db.add(ProductLocalStock(product_id=available.id, qty=3, warehouse_code="vitebsk"))
    tenant = Tenant(slug="accessory-tenant", display_name="Accessory Tenant")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Accessory Site", status="active")
    db.add(storefront)
    await db.flush()
    grant = TenantCatalogGrant(tenant_id=tenant.id, storefront_id=storefront.id, status="active", created_by_username="test", updated_by_username="test")
    db.add(grant)
    await db.flush()
    offer = TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id, product_id=available.id, catalog_grant_id=grant.id, price=345, old_price=400, is_published=True, created_by_username="test", updated_by_username="test")
    db.add(offer)
    await db.commit()
    await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=SeriesAccessoriesUpdate(accessory_product_ids=[item.id for item in accessories]))
    canonical = (await CatalogAccessoryService.resolve_public(db, [model], tenant_scope=CANONICAL))[model.id]
    assert [item.product_id for item in canonical] == [available.id, no_offer.id]
    assert canonical[0].price == available.price
    assert canonical[0].old_price == available.old_price
    assert canonical[0].availability_status == "in_stock_now"
    assert canonical[0].accessory_type == "wifi_module"
    assert canonical[0].suggested_for_purchase is True
    scope = TenantScope(tenant_id=tenant.id, storefront_id=storefront.id, is_canonical_storefront=False)
    scoped = (await CatalogAccessoryService.resolve_public(db, [model], tenant_scope=scope))[model.id]
    assert [item.product_id for item in scoped] == [available.id]
    assert (scoped[0].price, scoped[0].old_price) == (345, 400)
    assert {"vitebsk_qty", "minsk_qty", "supplier_id", "min_cost_byn"}.isdisjoint(scoped[0].model_dump())
    grant.status = "disabled"
    db.add(grant)
    await db.flush()
    assert (await CatalogAccessoryService.resolve_public(db, [model], tenant_scope=scope))[model.id] == []


@pytest.mark.asyncio
async def test_catalog_accessories_manager_kind_filter_precedes_pagination_and_counts(async_client, db):
    _, _, _, accessories = await _seed(db)
    db.add_all([Product(title=f"Accessory Module Non-accessory {i}", slug=f"accessory-non-{i}", price=1, product_kind="complete_split_system") for i in range(4)])
    await db.commit()
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await async_client.get("/api/manager/products/list", headers=headers, params={"search": "Accessory Module", "product_kind": "accessory", "sort": "price_asc", "limit": 1, "page": 2})
    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"page": 2, "limit": 1, "total": 3, "pages": 3}
    assert [item["id"] for item in response.json()["items"]] == [accessories[1].id]
    invalid = await async_client.get("/api/manager/products/list", headers=headers, params={"product_kind": "wifi_dongle"})
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_catalog_accessories_manager_workspace_api_and_duplicate_rejection(async_client, db):
    series, model, _, accessories = await _seed(db)
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    path = f"/api/manager/catalog-accessories/series/{series.id}"
    response = await async_client.put(path, headers=headers, json={"accessory_product_ids": [accessories[0].id]})
    assert response.status_code == 200, response.text
    product_path = f"/api/manager/catalog-accessories/products/{model.id}"
    inherited = await async_client.get(product_path, headers=headers)
    assert inherited.status_code == 200
    assert inherited.json()["items"][0]["inherited"] is True
    excluded = await async_client.put(product_path, headers=headers, json={"overrides": [{"accessory_product_id": accessories[0].id, "is_enabled": False}]})
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["items"][0]["is_enabled"] is False
    duplicate = await async_client.put(path, headers=headers, json={"accessory_product_ids": [accessories[0].id, accessories[0].id]})
    assert duplicate.status_code == 422


@pytest.mark.asyncio
async def test_catalog_accessories_manager_requires_auth_and_reports_missing_target(async_client, db):
    series, model, _, accessories = await _seed(db)
    path = f"/api/manager/catalog-accessories/series/{series.id}"
    before = await _state(db)
    unauthenticated = await async_client.put(path, json={"accessory_product_ids": [accessories[0].id]})
    assert unauthenticated.status_code == 401
    assert await _state(db) == before
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    missing = await async_client.get("/api/manager/catalog-accessories/products/987654321", headers=headers)
    assert missing.status_code == 404
    invalid = await async_client.put(path, headers=headers, json={"accessory_product_ids": [model.id]})
    assert invalid.status_code == 400
    assert await _state(db) == before


@pytest.mark.asyncio
async def test_catalog_accessories_public_detail_resolves_series_cards(async_client, db):
    series, model, _, accessories = await _seed(db)
    await CatalogAccessoryService.set_series_accessories(db, series_id=series.id, payload=SeriesAccessoriesUpdate(accessory_product_ids=[accessories[0].id]))
    response = await async_client.get(f"/api/v1/products/{model.slug}")
    assert response.status_code == 200, response.text
    card = response.json()["accessories"][0]
    assert card["product_id"] == accessories[0].id
    assert card["price"] == accessories[0].price
    assert card["compatibility_source"] == "series"
    assert card["suggested_for_purchase"] is True
