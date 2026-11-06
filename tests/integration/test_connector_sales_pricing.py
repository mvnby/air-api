"""Sales selection uses scoped public prices and the exact installation domain."""

from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import func, select

from core.command_actor import CommandActor
from models import (
    Brand, InstallationPreviewSnapshot, Product, ServiceEstimate, ServiceTariff,
    ServiceTariffRule, Tenant, TenantCatalogGrant, TenantOffer,
)
from models.catalog_accessory import ProductAccessoryOverride
from models.storefront_settings import StorefrontSettings
from models.tenancy import Storefront, TenantScope
from schemas_connector_sales_pricing import SalesInstallationInput, SalesSelectionInput
from schemas_storefront_settings import default_service_directions
from services.connector_sales_pricing import ConnectorSalesPricingService as Service
from services.installation_price_book_service import InstallationPriceBookService as Book


def _actor(tenant=1, storefront=1, *, canonical=True):
    return CommandActor(1, "sales-manager", TenantScope(
        tenant, storefront, is_system=canonical, is_canonical_storefront=canonical,
    ))


def _product(index, **overrides):
    values = dict(title=f"Sales split {index}", slug=f"sales-split-{index}", price=1000,
        product_kind="complete_split_system", power_cooling=2.6, is_inverter=True,
        specs={"area_m2": 25, "indoor_type": "настенный", "wifi_state": "ready", "__filter_min_heat": -25})
    values.update(overrides)
    return Product(**values)


def _installation(**values):
    return SalesInstallationInput(route_length_m="4.5", holes_by_type={"diamond": 2},
                                  access="standard", **values)


async def _book(db, actor, *, price=500, max_capacity="4", code="installation.wall", mode="fixed"):
    tariff = ServiceTariff(tenant_id=actor.tenant_scope.tenant_id, service_kind="installation",
        selector_label="Монтаж настенного комплекта", installation_code=code,
        installation_price_mode=mode,
        installation_match={"indoor_type": "wall", "match_strategy": "capacity_only", "capacity_min_kw": "2", "capacity_max_kw": max_capacity},
        base_price=price, included_route_meters=3, included_holes_by_type={"diamond": 1})
    db.add(tariff)
    await db.flush()
    db.add_all([
        ServiceTariffRule(tariff_id=tariff.id, rule_type="per_meter_over_included",
            component_code="route.extra_m", name="Трасса", unit="м", unit_price=10.25),
        ServiceTariffRule(tariff_id=tariff.id, rule_type="per_hole_manual",
            component_code="hole.diamond.extra", name="Отверстие", unit_price=50),
    ])
    await db.commit()
    await Book.publish(db, actor.tenant_scope, actor="sales-test")
    return tariff


@pytest.mark.asyncio
async def test_fractional_route_selected_accessories_full_budget_and_no_mutation(db):
    actor = _actor()
    product = _product(1)
    accessory = _product(2, price=125, product_kind="accessory", specs={"accessory_type": "wifi_module"})
    hidden = _product(3, price=1, product_kind="accessory", is_published=False)
    db.add_all([product, accessory, hidden])
    await db.flush()
    db.add_all([ProductAccessoryOverride(product_id=product.id, accessory_product_id=item.id, is_enabled=True)
                for item in (accessory, hidden)])
    await _book(db, actor)
    before = {model.__name__: await db.scalar(select(func.count()).select_from(model))
              for model in (InstallationPreviewSnapshot, ServiceEstimate)}
    result = await Service.select(db, actor, SalesSelectionInput(
        cooling_btu_class=9, budget_byn="1690.38", installation=_installation(),
        accessory_product_ids=[accessory.id],
    ))
    assert result.status == "ready"
    option = result.options[0]
    assert option.equipment_total_byn == Decimal("1000.00")
    assert option.installation_total_byn == Decimal("565.38")
    assert option.accessories_total_byn == Decimal("125.00")
    assert option.total_byn == Decimal("1690.38")
    assert [item.product_id for item in option.selected_accessories] == [accessory.id]
    assert [item.product_id for item in option.compatible_accessories] == [accessory.id]
    assert option.installation.preview_ref is None
    assert "1690.38 BYN" in result.message_text
    assert "wholesale" not in result.model_dump_json()
    for model in (InstallationPreviewSnapshot, ServiceEstimate):
        assert await db.scalar(select(func.count()).select_from(model)) == before[model.__name__]
    excluded = await Service.select(db, actor, SalesSelectionInput(
        cooling_btu_class=9, budget_byn="1690.37", installation=_installation(),
        accessory_product_ids=[accessory.id],
    ))
    assert excluded.options == []
    assert excluded.excluded_reasons == {"over_full_budget": 1}


@pytest.mark.asyncio
async def test_missing_inputs_missing_book_and_site_assessment_never_fabricate_total(db):
    actor = _actor()
    db.add(_product(1))
    await db.commit()
    missing = await Service.select(db, actor, SalesSelectionInput(cooling_btu_class=9))
    assert missing.status == "needs_input"
    assert set(missing.missing_inputs) == {"installation.route_length_m", "installation.holes_by_type", "installation.access"}
    assert missing.options == []
    no_book = await Service.select(db, actor, SalesSelectionInput(cooling_btu_class=9, installation=_installation()))
    assert no_book.status == "not_ready"
    assert no_book.excluded_reasons == {"price_book_not_published": 1}
    assessment = _installation().model_copy(update={"access": "requires_assessment"})
    site = await Service.select(db, actor, SalesSelectionInput(cooling_btu_class=9, installation=assessment))
    assert site.status == "not_ready"
    assert site.excluded_reasons == {"site_assessment_required": 1}
    assert "total_byn" not in site.model_dump_json()


@pytest.mark.asyncio
async def test_from_tariff_unknown_profile_and_unpriced_holes_not_ready(db):
    actor = _actor()
    product = _product(1)
    db.add(product)
    await _book(db, actor, mode="from")
    result = await Service.select(db, actor, SalesSelectionInput(cooling_btu_class=9, installation=_installation()))
    assert result.status == "not_ready"
    assert result.excluded_reasons == {"from": 1}
    assert result.options == []


@pytest.mark.asyncio
async def test_fingerprint_rejects_equipment_accessory_price_and_published_tariff_changes(db):
    actor = _actor()
    product, accessory = _product(1), _product(2, price=100, product_kind="accessory")
    db.add_all([product, accessory])
    await db.flush()
    db.add(ProductAccessoryOverride(product_id=product.id, accessory_product_id=accessory.id, is_enabled=True))
    tariff = await _book(db, actor)
    kwargs = dict(product_id=product.id, installation=_installation(), accessory_product_ids=[accessory.id])
    option = await Service.price_option(db, actor, **kwargs)
    repeated = await Service.price_option(db, actor, expected_fingerprint=option.calculation_fingerprint, **kwargs)
    assert repeated.calculation_fingerprint == option.calculation_fingerprint
    for item in (product, accessory):
        item.price += 1
        db.add(item)
        await db.commit()
        with pytest.raises(HTTPException) as changed:
            await Service.price_option(db, actor, expected_fingerprint=option.calculation_fingerprint, **kwargs)
        assert changed.value.status_code == 409
        assert changed.value.detail["code"] == "sales_price_changed"
        option = await Service.price_option(db, actor, **kwargs)
    tariff.base_price += 10
    db.add(tariff)
    await db.commit()
    # Draft edits do not change the published commercial calculation.
    assert (await Service.price_option(db, actor, **kwargs)).calculation_fingerprint == option.calculation_fingerprint
    await Book.publish(db, actor.tenant_scope, actor="sales-test")
    with pytest.raises(HTTPException) as changed:
        await Service.price_option(db, actor, expected_fingerprint=option.calculation_fingerprint, **kwargs)
    assert changed.value.status_code == 409
    accessory.is_published = False
    db.add(accessory)
    await db.commit()
    with pytest.raises(HTTPException) as hidden:
        await Service.price_option(db, actor, **kwargs)
    assert hidden.value.detail["code"] == "accessory_unavailable_or_incompatible"


@pytest.mark.asyncio
async def test_full_catalog_is_priced_before_brand_selection_and_hard_filters_remain(db):
    actor = _actor()
    brands = [Brand(title=f"Sales brand {i}", slug=f"sales-brand-{i}") for i in range(3)]
    db.add_all(brands)
    await db.flush()
    # Many cheap products fail strict tariff resolution; eligible later brands
    # must still be found without a top-N equipment-only shortlist.
    products = [_product(i, price=500, brand_id=brands[0].id,
        specs={"area_m2": 25, "indoor_type": "настенный", "capacity_cooling_kw": "unknown", "__filter_min_heat": -25})
        for i in range(105)]
    valid = [_product(200+i, price=1000+i, brand_id=brand.id) for i, brand in enumerate(brands)]
    bad = _product(300, price=1, brand_id=brands[0].id, specs={"area_m2": 25, "indoor_type": "настенный", "__filter_min_heat": -10})
    db.add_all([*products, *valid, bad])
    await _book(db, actor)
    result = await Service.select(db, actor, SalesSelectionInput(
        cooling_btu_class=9, heating_min_c=-25, budget_byn=2000, installation=_installation(),
    ))
    assert result.status == "ready"
    assert {item.product.product_id for item in result.options} == {item.id for item in valid}
    assert len({item.product.brand for item in result.options}) == 3
    assert result.excluded_reasons == {"missing_cooling_capacity": 105}
    assert result.matching_products == 108


@pytest.mark.asyncio
async def test_secondary_tenant_uses_own_offer_price_book_and_accessory_permissions(db):
    tenant = Tenant(slug="sales-secondary", display_name="Sales secondary")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Sales secondary", status="active")
    db.add(storefront)
    await db.flush()
    actor = _actor(tenant.id, storefront.id, canonical=False)
    db.add(StorefrontSettings(tenant_id=tenant.id, storefront_id=storefront.id,
        display_name="Sales secondary", services=[item.model_dump() for item in default_service_directions(enabled=True)]))
    grant = TenantCatalogGrant(tenant_id=tenant.id, storefront_id=storefront.id, status="active",
        created_by_username="test", updated_by_username="test")
    db.add(grant)
    product = _product(1, price=9999)
    accessory = _product(2, price=1111, product_kind="accessory")
    db.add_all([product, accessory])
    await db.flush()
    offer = TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id, catalog_grant_id=grant.id,
        product_id=product.id, price=600, is_published=True, created_by_username="test", updated_by_username="test")
    db.add(offer)
    db.add(ProductAccessoryOverride(product_id=product.id, accessory_product_id=accessory.id, is_enabled=True))
    await _book(db, actor, price=700)
    from dataclasses import replace
    from models import GlobalConfig
    db.add(GlobalConfig(key="install_discount", value="100"))
    await db.commit()
    # A partner's stale positive hint cannot select canonical prices or discounts.
    actor = replace(actor, tenant_scope=replace(actor.tenant_scope, is_canonical_storefront=True))
    option = await Service.price_option(db, actor, product_id=product.id, installation=_installation())
    assert option.equipment_total_byn == Decimal("600.00")
    assert option.installation_total_byn == Decimal("765.38")
    assert option.compatible_accessories == []
    assert option.product.site_url is None
    assert "9999" not in option.model_dump_json()
    assert "1111" not in option.model_dump_json()
    offer.is_published = False
    db.add(offer)
    await db.commit()
    with pytest.raises(HTTPException) as hidden:
        await Service.price_option(db, actor, product_id=product.id, installation=_installation())
    assert hidden.value.status_code == 404


@pytest.mark.parametrize("values", [
    {"quantity": 2}, {"budget_scope": "per_unit"}, {"accessory_product_ids": [1, 1]},
    {"installation": {"holes_by_type": {"diamond": "0.5"}}},
])
def test_bounded_input_rejects_ambiguous_or_invalid_work(values):
    with pytest.raises(ValidationError):
        SalesSelectionInput(cooling_btu_class=9, **values)


@pytest.mark.asyncio
async def test_request_local_book_reads_match_ordinary_preview_and_cannot_persist(db):
    actor = _actor()
    product = _product(1, main_image="https://images.example.test/real-product.webp")
    db.add(product)
    await _book(db, actor)
    payload = Service.preview_payload(product.id, _installation())
    context = await Book.read_context(db, actor.tenant_scope, {product.id})
    ordinary = await Book.preview(db, actor.tenant_scope, payload, persist=False)
    batched = await Book.preview(db, actor.tenant_scope, payload, persist=False, _read_context=context)
    assert batched == ordinary
    with pytest.raises(ValueError, match="persistent preview"):
        await Book.preview(db, actor.tenant_scope, payload, persist=True,
                           idempotency_key="must-not-store-cached-data", _read_context=context)
    foreign_scope = TenantScope(2, 2, is_system=False, is_canonical_storefront=False)
    with pytest.raises(ValueError, match="another scope"):
        await Book.preview(db, foreign_scope, payload, persist=False, _read_context=context)
    result = await Service.select(db, actor, SalesSelectionInput(cooling_btu_class=9, installation=_installation()))
    repriced = await Service.price_option(db, actor, product_id=product.id, installation=_installation())
    assert result.options[0].calculation_fingerprint == repriced.calculation_fingerprint
    assert result.options[0].image_url == "https://images.example.test/real-product.webp"


@pytest.mark.asyncio
async def test_oauth_actor_without_canonical_hint_keeps_native_catalog_discount(db):
    from dataclasses import replace
    from models import GlobalConfig

    actor = replace(_actor(), tenant_scope=replace(_actor().tenant_scope, is_canonical_storefront=None))
    product = _product(1)
    db.add_all([product, GlobalConfig(key="install_discount", value="100")])
    await _book(db, actor)
    installation = _installation()
    verified = await Service.verified_actor(db, actor)
    native = await Book.preview(db, verified.tenant_scope,
        Service.preview_payload(product.id, installation), persist=False)
    assert native.total == Decimal("465.38")
    preview = await Service.price_option(db, actor, product_id=product.id, installation=installation)
    assert preview.installation_total_byn == native.total
    selected = await Service.select(db, actor, SalesSelectionInput(
        cooling_btu_class=9, budget_byn="1465.38", installation=installation,
    ))
    assert selected.options[0].total_byn == Decimal("1465.38")
    assert selected.options[0].calculation_fingerprint == preview.calculation_fingerprint
    # A stale negative hint must not suppress the server-owned canonical policy.
    wrong_hint = replace(actor, tenant_scope=replace(actor.tenant_scope, is_canonical_storefront=False))
    repeated = await Service.price_option(db, wrong_hint, product_id=product.id, installation=installation)
    assert repeated.calculation_fingerprint == preview.calculation_fingerprint
    # The batching helper is independently safe when called with raw OAuth scope.
    context = await Book.read_context(db, actor.tenant_scope, {product.id})
    cached = await Book.preview(db, actor.tenant_scope, Service.preview_payload(product.id, installation),
                               persist=False, _read_context=context)
    assert cached == native
