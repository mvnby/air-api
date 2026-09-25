"""PostgreSQL contract tests for scoped publication and immutable previews."""

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlmodel import select

from models import InstallationPriceBook, InstallationPreviewSnapshot, ServiceTariff, ServiceTariffRule, Storefront, Tenant
from models.tenancy import TenantScope
from schemas_installation_price_book import InstallationPreviewPayload, InstallationResolvePayload
from services.installation_price_book_service import InstallationPriceBookService as BookService


async def _scope(db, slug):
    tenant = Tenant(slug=slug, display_name=slug, status="active", is_system=False)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name=slug,
                            status="active", is_default=True)
    db.add(storefront)
    await db.flush()
    return TenantScope(tenant_id=tenant.id, storefront_id=storefront.id,
                       is_system=False, is_canonical_storefront=False)


async def _draft(db, scope, *, price):
    tariff = ServiceTariff(tenant_id=scope.tenant_id, service_kind="installation",
        selector_label="Монтаж настенного комплекта", short_name="Монтаж настенного комплекта",
        installation_code="installation.wall.2_4", installation_price_mode="fixed",
        installation_match={"indoor_type": "wall", "capacity_min_kw": "2", "capacity_max_kw": "4",
                            "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        base_price=price, included_route_meters=3, included_holes_by_type={"diamond": 1})
    db.add(tariff)
    await db.flush()
    db.add_all([
        ServiceTariffRule(tariff_id=tariff.id, rule_type="per_meter_over_included",
                          component_code="route.extra_m", name="Трасса", unit="м", unit_price=10.25),
        ServiceTariffRule(tariff_id=tariff.id, rule_type="per_hole_manual",
                          component_code="hole.diamond.extra", name="Алмазное отверстие", unit_price=50),
    ])
    await db.commit()
    return tariff


@pytest.mark.asyncio
async def test_publication_is_tenant_scoped_and_old_preview_survives_draft_edit(db):
    a = await _scope(db, "installation-book-a")
    b = await _scope(db, "installation-book-b")
    tariff_a = await _draft(db, a, price=500)
    await _draft(db, b, price=700)
    published_a = await BookService.publish(db, a, actor="manager-a")
    published_b = await BookService.publish(db, b, actor="manager-b")
    assert published_a.revision == published_b.revision == 1
    assert published_a.price_book_id != published_b.price_book_id

    profile = {"product_kind": "complete_split_system", "indoor_type": "wall",
               "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"', "pipe_gas": '3/8"', "confirmed": True}
    target = InstallationResolvePayload(typed_profile=profile)
    resolved_a, _ = await BookService.resolve(db, a, target)
    resolved_b, _ = await BookService.resolve(db, b, target)
    assert resolved_a.base_price == Decimal("500")
    assert resolved_b.base_price == Decimal("700")
    assert resolved_a.scope_ref != resolved_b.scope_ref

    payload = InstallationPreviewPayload.model_validate({"installations": [
        {"key": "one", "typed_profile": profile, "route_length_m": "6", "holes_by_type": {"diamond": 2}}
    ], "expected_revision": 1})
    preview = await BookService.preview(db, a, payload)
    assert preview.total == Decimal("580.75")
    assert preview.preview_ref
    saved = (await db.execute(select(InstallationPreviewSnapshot).where(
        InstallationPreviewSnapshot.tenant_id == a.tenant_id))).scalar_one()
    assert saved.storefront_id == a.storefront_id
    assert saved.snapshot["result"]["total"] == "580.75"
    assert saved.token_hash != preview.preview_ref

    tariff_a.base_price = 550
    db.add(tariff_a)
    await db.commit()
    second = await BookService.publish(db, a, actor="manager-a")
    assert second.revision == 2
    old = (await db.execute(select(InstallationPriceBook).where(
        InstallationPriceBook.id == published_a.price_book_id))).scalar_one()
    assert old.entries[0]["base_price"] == "500.00"
    assert saved.snapshot["result"]["total"] == "580.75"
    with pytest.raises(HTTPException) as error:
        await BookService.preview(db, a, payload)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "price_changed"
    assert (await BookService.latest(db, b)).revision == 1
    tariff_a.installation_match = {**tariff_a.installation_match, "capacity_max_kw": "5"}
    db.add(tariff_a)
    await db.commit()
    with pytest.raises(HTTPException) as semantic_error:
        await BookService.publish(db, a, actor="manager-a")
    assert semantic_error.value.detail["code"] == "tariff_code_reused"


@pytest.mark.asyncio
async def test_equal_matcher_conflict_rejects_publication_without_replacing_revision(db):
    scope = await _scope(db, "installation-book-conflict")
    await _draft(db, scope, price=500)
    first = await BookService.publish(db, scope, actor="manager")
    duplicate = ServiceTariff(tenant_id=scope.tenant_id, service_kind="installation",
        selector_label="Конфликт", installation_code="installation.wall.duplicate",
        installation_match={"indoor_type": "wall", "capacity_min_kw": "2", "capacity_max_kw": "4",
                            "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        base_price=510, included_route_meters=3)
    db.add(duplicate)
    await db.flush()
    db.add(ServiceTariffRule(tariff_id=duplicate.id, rule_type="per_meter_over_included",
        component_code="route.extra_m", name="Трасса", unit="м", unit_price=10))
    await db.commit()
    with pytest.raises(HTTPException) as error:
        await BookService.publish(db, scope, actor="manager")
    assert error.value.detail["code"] == "matcher_conflict"
    assert (await BookService.latest(db, scope)).id == first.price_book_id


@pytest.mark.asyncio
async def test_public_resolve_preview_hide_disabled_direction_and_cache_privately(async_client, db):
    from main import app
    from core.tenant_scope import get_public_tenant_scope
    from models.storefront_settings import StorefrontSettings
    from schemas_storefront_settings import default_service_directions

    scope = await _scope(db, "installation-book-public")
    await _draft(db, scope, price=500)
    await BookService.publish(db, scope, actor="manager")
    services = [item.model_dump() for item in default_service_directions(enabled=False)]
    next(item for item in services if item["key"] == "installation")["enabled"] = True
    settings = StorefrontSettings(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
        display_name="Installation public", services=services)
    db.add(settings)
    await db.commit()
    app.dependency_overrides[get_public_tenant_scope] = lambda: scope
    profile = {"product_kind": "complete_split_system", "indoor_type": "wall",
               "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"', "pipe_gas": '3/8"', "confirmed": True}
    resolved = await async_client.post("/api/v1/service-pricing/installation/resolve", json={"typed_profile": profile})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "fixed"
    assert resolved.headers["cache-control"] == "private, no-store"
    preview = await async_client.post("/api/v1/service-pricing/installation/preview", json={
        "installations": [{"key": "one", "typed_profile": profile, "route_length_m": "6"}]
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["total"] == "530.75"
    assert preview.headers["cache-control"] == "private, no-store"
    settings.services[0]["enabled"] = False
    db.add(settings)
    await db.commit()
    disabled = await async_client.post("/api/v1/service-pricing/installation/resolve", json={"typed_profile": profile})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "unavailable"
    assert disabled.json()["price_book_id"] is None
