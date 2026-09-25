"""A published book retires old public installation pricing without hiding other services."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from models.tenancy import TenantScope
from models import ServiceTariff
from routers import api_content, api_service_pricing
from schemas import ManagerTariffServiceKind
from schemas_service_catalog import PublicServiceEstimateCalculatePayload
from services.content_api_service import ContentApiService
from services.installation_price_book_service import InstallationPriceBookService
from services.installation_pricing_service import InstallationPricingError, InstallationPricingService
from services.installation_service import InstallationService
from services.service_estimate_service import ServiceEstimateService
from services.storefront_settings_service import StorefrontSettingsService
from services.tariffs_service import TariffsService


@pytest.fixture
def book_stubs(monkeypatch):
    state = {"book": SimpleNamespace(revision=7), "enabled": True}

    async def latest(_session, _scope):
        return state["book"]

    async def enabled(_session, **_kwargs):
        return state["enabled"]

    monkeypatch.setattr(InstallationPriceBookService, "latest", latest)
    monkeypatch.setattr(StorefrontSettingsService, "is_service_enabled", enabled)
    return state


@pytest.mark.asyncio
async def test_config_exposes_scope_bound_source_and_only_supported_checkout(book_stubs):
    canonical = TenantScope(tenant_id=1, storefront_id=2, is_system=True,
                            is_canonical_storefront=True)
    partner = TenantScope(tenant_id=3, storefront_id=4,
                          is_canonical_storefront=False)
    response = Response()
    main = await api_service_pricing.get_public_installation_pricing_config(
        response, None, canonical)
    assert main.source == "price_book" and main.price_book_revision == 7
    assert main.capabilities.standard_product_acceptance
    assert not main.capabilities.legacy_rate_checkout
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"
    partner_config = await api_service_pricing.get_public_installation_pricing_config(
        Response(), None, partner)
    assert partner_config.source == "price_book"
    assert not partner_config.capabilities.standard_product_acceptance
    assert partner_config.capabilities.multisplit_preview_only
    book_stubs["book"] = None
    legacy = await api_service_pricing.get_public_installation_pricing_config(
        Response(), None, canonical)
    assert legacy.source == "legacy" and legacy.price_book_revision is None
    assert legacy.capabilities.legacy_rate_checkout
    book_stubs["enabled"] = False
    disabled = await api_service_pricing.get_public_installation_pricing_config(
        Response(), None, canonical)
    assert disabled.source == "legacy"
    assert not any(disabled.capabilities.model_dump().values())


@pytest.mark.asyncio
async def test_legacy_rate_list_and_checkout_require_book_preview(book_stubs, monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=2, is_canonical_storefront=True)
    with pytest.raises(HTTPException) as rates:
        await api_content.get_installation_rates(None, scope)
    assert rates.value.status_code == 409
    assert rates.value.detail["code"] == "book_preview_required"
    with pytest.raises(InstallationPricingError) as checkout:
        await InstallationPricingService.price_public_items(
            None, [SimpleNamespace(with_installation=True)], tenant_scope=scope)
    assert checkout.value.code == "book_preview_required"

    async def old_rates(_session, _scope):
        return ["legacy-rate"]

    monkeypatch.setattr(InstallationService, "get_all", old_rates)
    book_stubs["book"] = None
    assert await api_content.get_installation_rates(None, scope) == ["legacy-rate"]


@pytest.mark.asyncio
async def test_old_installation_tariff_list_and_calculate_block_after_book(book_stubs, monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=2, is_canonical_storefront=True)
    with pytest.raises(HTTPException) as listed:
        await api_service_pricing.list_public_service_tariffs(
            ManagerTariffServiceKind.installation, None, scope)
    assert listed.value.status_code == 409
    assert listed.value.detail["code"] == "book_preview_required"

    async def tariff(_session, _id, _scope, *, require_active):
        return SimpleNamespace(service_kind="installation")

    monkeypatch.setattr(TariffsService, "get_tariff_by_id", tariff)
    payload = PublicServiceEstimateCalculatePayload(tariff_id=5)
    with pytest.raises(HTTPException) as calculated:
        await api_service_pricing.calculate_public_service_tariff(payload, None, scope)
    assert calculated.value.status_code == 409
    assert calculated.value.detail["code"] == "book_preview_required"

    async def other_tariffs(_session, **_kwargs):
        return [ServiceTariff(id=9, service_kind="maintenance", selector_label="Обслуживание",
                              base_price=100)]

    monkeypatch.setattr(TariffsService, "get_all_tariffs", other_tariffs)
    other_list = await api_service_pricing.list_public_service_tariffs(
        ManagerTariffServiceKind.maintenance, None, scope)
    assert len(other_list.items) == 1 and other_list.items[0].base_price == 100

    async def repair_tariff(_session, _id, _scope, *, require_active):
        return SimpleNamespace(service_kind="repair")

    async def estimate(_session, _payload, _scope):
        return "repair-price"

    monkeypatch.setattr(TariffsService, "get_tariff_by_id", repair_tariff)
    monkeypatch.setattr(ServiceEstimateService, "calculate_install_estimate", estimate)
    assert await api_service_pricing.calculate_public_service_tariff(payload, None, scope) == "repair-price"


@pytest.mark.asyncio
async def test_mixed_service_list_filters_only_old_installation_service_prices(book_stubs, monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=2, is_canonical_storefront=True)

    async def services(_session, **_kwargs):
        return [{"category": "installation_option", "slug": "old-pump"},
                {"category": "installation", "slug": "old-install"},
                {"category": "maintenance", "slug": "maintenance"}]

    async def options(_session, **_kwargs):
        return [{"category": "maintenance", "slug": "maintenance"}]

    monkeypatch.setattr(ContentApiService, "get_active_services", services)
    monkeypatch.setattr(ContentApiService, "get_service_options", options)
    result = await api_content.get_services(Response(), None, scope)
    assert [item["slug"] for item in result] == ["maintenance"]
    with pytest.raises(HTTPException) as old_options:
        await api_content.get_service_options(Response(), "installation_option", None, scope)
    assert old_options.value.detail["code"] == "book_preview_required"
    assert await api_content.get_service_options(Response(), "maintenance", None, scope) == [
        {"category": "maintenance", "slug": "maintenance"}]
    book_stubs["book"] = None
    assert len(await api_content.get_services(Response(), None, scope)) == 3
