from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from core.command_actor import CommandActor
from crud.connector_catalog_selection import ConnectorCatalogSelectionDAO
from models.tenancy import TenantScope
from schemas_connector_catalog import CatalogProduct, CatalogSelectionInput, CatalogSelectionOption
from services.connector_catalog_selection_service import ConnectorCatalogSelectionService


def test_secondary_projection_never_reads_master_or_supplier_prices():
    candidates = ConnectorCatalogSelectionDAO.candidates(
        SimpleNamespace(bind=None), tenant_scope=TenantScope(tenant_id=7, storefront_id=12, is_system=True),
        canonical=False, cooling_btu_class=9, quantity=3, max_unit_price=500,
    )
    sql = str(candidates.select().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "tenant_offer.price <= 500" in sql
    assert "tenant_offer.tenant_id = 7" in sql
    assert "tenant_offer.storefront_id = 12" in sql
    assert "tenant_catalog_grant.status = 'active'" in sql
    assert "tenant_offer.catalog_grant_id IS NULL" not in sql
    assert "product.price" not in sql
    assert "wholesale" not in sql
    assert "rrc_byn" not in sql
    assert "supplier.is_active IS true" in sql
    assert "supplier_offer.qty > 0" in sql


def test_client_message_keeps_alternatives_and_installation_separate():
    product = CatalogProduct(
        product_id=1, title="Model", brand="Brand", series=None, unit_price_byn=1200,
        site_url="https://seller.test/product/model/", is_inverter=True,
        cooling_power_kw=2.6, area_m2=25, heating_min_c=None, wifi="unknown", availability="on_request",
    )
    options = [CatalogSelectionOption(label="Brand", reason="Match", product=product, quantity=2, equipment_total_byn=2400)]
    text = ConnectorCatalogSelectionService._message(options, [], datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    assert "10.10.2026 15:00 (Минск)" in text
    assert "1200 BYN за шт. × 2 шт. = 2400 BYN" in text
    assert "их суммы не складываются" in text
    assert "Монтаж не включён" in text
    assert "Wi-Fi не указан" in text
    assert "обогрев" not in text
    assert "https://seller.test/product/model/" in text
    assert "Наличие и срок поставки уточняются" in text


@pytest.mark.asyncio
async def test_secondary_without_verified_domain_has_no_other_sellers_link(monkeypatch):
    async def no_domains(session, tenant_scope):
        return []

    monkeypatch.setattr(ConnectorCatalogSelectionDAO, "verified_domains", no_domains)
    actor = CommandActor(1, "manager", TenantScope(7, 12, is_system=True))
    assert await ConnectorCatalogSelectionService._site_base(None, actor, False) is None


@pytest.mark.asyncio
async def test_verified_domains_use_the_existing_hostname_validation(monkeypatch):
    async def domains(session, tenant_scope):
        return ["https://foreign.test", "seller.test\\evil", "normal.test"]

    monkeypatch.setattr(ConnectorCatalogSelectionDAO, "verified_domains", domains)
    actor = CommandActor(1, "manager", TenantScope(7, 12))
    assert await ConnectorCatalogSelectionService._site_base(None, actor, False) == "https://normal.test"


def test_area_only_bounds_use_the_existing_sizing_ranges():
    assert ConnectorCatalogSelectionService._area_ceiling(CatalogSelectionInput(area_m2=20)) == 24
    assert ConnectorCatalogSelectionService._area_ceiling(CatalogSelectionInput(area_m2=30)) == 32
    assert ConnectorCatalogSelectionService._area_ceiling(CatalogSelectionInput(area_m2=20, cooling_btu_class=12)) is None


@pytest.mark.parametrize("site_base", ["https://mvn.by", "https://verified-seller.test"])
@pytest.mark.parametrize("slug, path", [
    ("tcc09zhrhdv", "/product/tcc09zhrhdv/"),
    ("model?query=1", "/product/model%3Fquery%3D1/"),
])
def test_product_links_use_authoritative_route_and_encode_slug(site_base, slug, path):
    row = dict(
        product_id=1, title="Model", slug=slug, brand=None, series=None,
        unit_price_byn=1200, is_inverter=True, cooling_power_kw=2.6,
        area_m2=25, heating_min_c=None, wifi="unknown", enough_stock=False,
    )
    product = ConnectorCatalogSelectionService._product(row, site_base)
    assert product.site_url == f"{site_base}{path}"
    assert ConnectorCatalogSelectionService._product(row, None).site_url is None
