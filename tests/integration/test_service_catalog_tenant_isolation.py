from datetime import timedelta

import pytest
from sqlmodel import select

from core.security import create_access_token
from models import (
    InstallationRate,
    Service,
    ServiceEstimate,
    ServiceTariff,
    ServiceTariffRule,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
    TenantOffer,
)
from models.storefront_settings import StorefrontSettings
from models.tenancy import TenantScope
from core.tenant_scope import get_public_tenant_scope
from schemas import OrderPayload
from schemas_storefront_settings import default_service_directions
from services.installation_pricing_service import InstallationPricingError
from services.service_catalog_template_service import ServiceCatalogTemplateService
from services.tariffs_service import TariffsService
from services.website_order_service import WebsiteOrderService


async def _tenant_scope(db, *, slug: str) -> TenantScope:
    tenant = Tenant(slug=slug, display_name=slug, status="active", is_system=False)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="main",
        display_name=slug,
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    return TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_system=False,
        is_canonical_storefront=False,
    )


async def _manager_headers(db, *, tenant_id: int, username: str) -> dict[str, str]:
    user = StaffUser(
        display_name=username,
        status="active",
        roles=["manager"],
        primary_role="manager",
        username=username,
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=int(user.id),
            role="manager",
            status="active",
        )
    )
    await db.flush()
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "auth_source": "service-catalog-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_detached_service_template_clone_is_idempotent_and_tenant_isolated(db):
    source_service = Service(
        title="Виброопоры",
        slug="vibration-stand",
        category="installation_option",
        is_active=True,
        base_price=80,
    )
    source_tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж 12",
        estimate_template="Монтаж 12",
        short_name="Монтаж 12",
        category="Wall",
        power_range="12",
        base_price=500,
        installation_code="installation.wall.legacy_template",
        installation_match={"indoor_type": "wall", "capacity_max_kw": "4", "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        installation_price_mode="from",
        included_holes_by_type={"diamond": 1},
        included_route_meters=3,
        is_active=True,
    )
    source_rate = InstallationRate(
        category="Wall",
        power_range="12",
        base_price=500,
        extra_pipe_price=40,
        included_pipe_meters=3,
        is_fixed=True,
    )
    db.add_all([source_service, source_tariff, source_rate])
    await db.flush()
    source_rule = ServiceTariffRule(
        tariff_id=int(source_tariff.id),
        rule_type="per_unit_manual",
        name="Виброопоры",
        unit_price=80,
        component_code="pump.install",
        service_id=int(source_service.id),
        is_active=True,
    )
    db.add(source_rule)
    await db.commit()

    target = await _tenant_scope(db, slug="service-target")
    foreign = await _tenant_scope(db, slug="service-foreign")
    await db.commit()

    preview = await ServiceCatalogTemplateService.preview(
        db,
        tenant_scope=target,
    )
    assert preview.source_counts.model_dump() == {
        "services": 1,
        "tariffs": 1,
        "tariff_rules": 1,
        "installation_rates": 1,
    }
    assert preview.can_clone is True

    cloned = await ServiceCatalogTemplateService.clone(
        db,
        tenant_scope=target,
        expected_fingerprint=preview.source_fingerprint,
    )
    assert cloned.status == "cloned"

    target_tariffs = await TariffsService.get_all_tariffs(
        db,
        tenant_scope=target,
    )
    canonical_tariffs = await TariffsService.get_all_tariffs(db)
    foreign_tariffs = await TariffsService.get_all_tariffs(
        db,
        tenant_scope=foreign,
    )
    assert [row.id for row in canonical_tariffs] == [source_tariff.id]
    assert len(target_tariffs) == 1
    assert foreign_tariffs == []
    target_tariff = target_tariffs[0]
    assert target_tariff.source_tariff_id == source_tariff.id
    assert target_tariff.installation_code == source_tariff.installation_code
    assert target_tariff.installation_match == source_tariff.installation_match
    assert target_tariff.included_holes_by_type == {"diamond": 1}
    assert target_tariff.rules[0].source_rule_id == source_rule.id
    assert target_tariff.rules[0].component_code == "pump.install"

    target_service = (
        await db.execute(
            select(Service).where(Service.tenant_id == target.tenant_id)
        )
    ).scalar_one()
    assert target_tariff.rules[0].service_id == target_service.id
    assert target_service.source_service_id == source_service.id

    target_tariff.base_price = 777
    local_addition = Service(
        tenant_id=target.tenant_id,
        title="Локальная услуга",
        slug="local-addon",
        category="maintenance",
        base_price=125,
    )
    db.add_all([target_tariff, local_addition])
    await db.commit()
    repeated = await ServiceCatalogTemplateService.clone(
        db,
        tenant_scope=target,
        expected_fingerprint=preview.source_fingerprint,
    )
    # Idempotence means every detached source row is still present. Local edits
    # and additional source-less rows are intentionally outside that check.
    assert repeated.status == "already_cloned"
    await db.refresh(target_tariff)
    await db.refresh(local_addition)
    assert target_tariff.base_price == 777
    assert local_addition.title == "Локальная услуга"


@pytest.mark.asyncio
async def test_template_clone_rejects_partial_local_catalog_without_overwrite(db):
    db.add(
        ServiceTariff(
            service_kind="repair",
            selector_label="Диагностика",
            estimate_template="Диагностика",
            short_name="Диагностика",
            base_price=100,
        )
    )
    target = await _tenant_scope(db, slug="partial-target")
    await db.flush()
    local = Service(
        tenant_id=target.tenant_id,
        title="Своя услуга",
        slug="local-service",
        category="installation_option",
        base_price=25,
    )
    db.add(local)
    await db.commit()

    preview = await ServiceCatalogTemplateService.preview(db, tenant_scope=target)
    assert preview.can_clone is False
    with pytest.raises(Exception) as exc_info:
        await ServiceCatalogTemplateService.clone(
            db,
            tenant_scope=target,
            expected_fingerprint=preview.source_fingerprint,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    await db.refresh(local)
    assert local.title == "Своя услуга"


@pytest.mark.asyncio
async def test_public_service_pricing_uses_only_enabled_tenant_tariffs(
    async_client,
    db,
):
    from main import app

    source = ServiceTariff(
        service_kind="installation",
        selector_label="Канонический монтаж",
        estimate_template="Канонический монтаж",
        short_name="Канонический монтаж",
        base_price=500,
        is_active=True,
    )
    source_option = Service(
        title="Виброопоры",
        slug="public-vibration-stand",
        category="installation_option",
        is_active=True,
        base_price=80,
    )
    source_rate = InstallationRate(
        category="Wall",
        power_range="12",
        base_price=500,
        extra_pipe_price=40,
        included_pipe_meters=3,
        is_fixed=True,
    )
    db.add_all([source, source_option, source_rate])
    await db.commit()
    target = await _tenant_scope(db, slug="public-pricing-target")
    await db.commit()
    preview = await ServiceCatalogTemplateService.preview(db, tenant_scope=target)
    await ServiceCatalogTemplateService.clone(
        db,
        tenant_scope=target,
        expected_fingerprint=preview.source_fingerprint,
    )
    cloned = (
        await db.execute(
            select(ServiceTariff).where(ServiceTariff.tenant_id == target.tenant_id)
        )
    ).scalar_one()
    cloned.base_price = 725
    settings = StorefrontSettings(
        tenant_id=target.tenant_id,
        storefront_id=target.storefront_id,
        display_name="Public pricing target",
        services=[
            item.model_dump()
            for item in default_service_directions(enabled=False)
        ],
    )
    settings.services[0]["enabled"] = True
    db.add_all([cloned, settings])
    await db.commit()
    app.dependency_overrides[get_public_tenant_scope] = lambda: target

    listed = await async_client.get(
        "/api/v1/service-pricing/tariffs",
        params={"service_kind": "installation"},
    )
    assert listed.status_code == 200, listed.text
    assert [(item["id"], item["base_price"]) for item in listed.json()["items"]] == [
        (cloned.id, 725)
    ]

    services = await async_client.get("/api/v1/content/services")
    options = await async_client.get("/api/v1/services/options")
    rates = await async_client.get("/api/v1/installation-rates")
    assert [item["slug"] for item in services.json()] == [source_option.slug]
    assert [item["slug"] for item in options.json()] == [source_option.slug]
    assert [item["base_price"] for item in rates.json()] == [source_rate.base_price]

    calculated = await async_client.post(
        "/api/v1/service-pricing/calculate",
        json={"tariff_id": cloned.id, "route_length_m": 3, "quantity": 2},
    )
    assert calculated.status_code == 200, calculated.text
    assert calculated.json()["total"] == 1450

    settings.services[0]["enabled"] = False
    db.add(settings)
    await db.commit()
    disabled = await async_client.get(
        "/api/v1/service-pricing/tariffs",
        params={"service_kind": "installation"},
    )
    assert disabled.status_code == 404
    assert (await async_client.get("/api/v1/content/services")).json() == []
    assert (await async_client.get("/api/v1/services/options")).json() == []
    assert (await async_client.get("/api/v1/installation-rates")).json() == []


@pytest.mark.asyncio
async def test_manager_service_catalog_returns_foreign_resources_as_not_found(
    async_client,
    db,
):
    target = await _tenant_scope(db, slug="manager-service-target")
    foreign = await _tenant_scope(db, slug="manager-service-foreign")
    headers = await _manager_headers(
        db,
        tenant_id=target.tenant_id,
        username="manager-service-target",
    )
    own_tariff = ServiceTariff(
        tenant_id=target.tenant_id,
        service_kind="installation",
        selector_label="Свой монтаж",
        estimate_template="Свой монтаж",
        short_name="Свой монтаж",
        base_price=700,
    )
    foreign_tariff = ServiceTariff(
        tenant_id=foreign.tenant_id,
        service_kind="installation",
        selector_label="Чужой монтаж",
        estimate_template="Чужой монтаж",
        short_name="Чужой монтаж",
        base_price=900,
    )
    own_rate = InstallationRate(
        tenant_id=target.tenant_id,
        category="Wall",
        power_range="07-12",
        base_price=700,
    )
    foreign_rate = InstallationRate(
        tenant_id=foreign.tenant_id,
        category="Wall",
        power_range="07-12",
        base_price=900,
    )
    db.add_all([own_tariff, foreign_tariff, own_rate, foreign_rate])
    await db.flush()
    own_estimate = ServiceEstimate(
        tenant_id=target.tenant_id,
        tariff_id=own_tariff.id,
        title="Своя смета",
        total=700,
    )
    foreign_estimate = ServiceEstimate(
        tenant_id=foreign.tenant_id,
        tariff_id=foreign_tariff.id,
        title="Чужая смета",
        total=900,
    )
    db.add_all([own_estimate, foreign_estimate])
    await db.commit()

    tariffs = await async_client.get("/api/manager/tariffs", headers=headers)
    rates = await async_client.get(
        "/api/manager/installation-rates",
        headers=headers,
    )
    estimates = await async_client.get(
        "/api/manager/service-estimates",
        headers=headers,
    )
    assert tariffs.status_code == rates.status_code == estimates.status_code == 200
    assert [item["id"] for item in tariffs.json()["items"]] == [own_tariff.id]
    assert [item["id"] for item in rates.json()["items"]] == [own_rate.id]
    assert [item["id"] for item in estimates.json()["items"]] == [own_estimate.id]

    foreign_calculation = await async_client.post(
        "/api/manager/service-estimates/calculate",
        headers=headers,
        json={"tariff_id": foreign_tariff.id},
    )
    foreign_rate_update = await async_client.put(
        f"/api/manager/installation-rates/{foreign_rate.id}",
        headers=headers,
        json={
            "base_price": 1,
            "extra_pipe_price": 0,
            "included_pipe_meters": 3,
        },
    )
    foreign_estimate_read = await async_client.get(
        f"/api/manager/service-estimates/{foreign_estimate.id}",
        headers=headers,
    )
    assert foreign_calculation.status_code == 404
    assert foreign_rate_update.status_code == 404
    assert foreign_estimate_read.status_code == 404


@pytest.mark.asyncio
async def test_checkout_rejects_installation_when_tenant_direction_is_disabled(db):
    from models import Product

    target = await _tenant_scope(db, slug="disabled-checkout-target")
    product = Product(
        title="Tenant product",
        slug="tenant-product",
        price=1500,
        is_published=True,
    )
    db.add(product)
    await db.flush()
    db.add(
        TenantOffer(
            tenant_id=target.tenant_id,
            storefront_id=target.storefront_id,
            product_id=int(product.id),
            price=1600,
            is_published=True,
            status="active",
            created_by_username="test",
            updated_by_username="test",
        )
    )
    await db.commit()
    payload = OrderPayload.model_validate(
        {
            "customer": {"name": "Покупатель", "phone": "+375291112233"},
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_options": [],
                }
            ],
        }
    )

    with pytest.raises(InstallationPricingError) as exc_info:
        await WebsiteOrderService._create_order_mutation(
            db,
            payload,
            tenant_scope=target,
            request_key_hash="test-request-key",
        )
    assert exc_info.value.code == "installation_not_available"
