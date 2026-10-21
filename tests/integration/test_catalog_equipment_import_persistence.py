import pytest

from models import Product
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.importer_service import ImporterService
from services.product_write_service import ProductWriteService
from models.tenancy import TenantScope


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_import_derives_kinghome_complete_and_retains_repair_on_reimport_and_save(db, monkeypatch):
    class Parser:
        def supports(self, url):
            return True

        async def parse(self, url):
            return {
                "title": "KINGHOME KUD100ZD1/A-S + KUD100W1/NhA-S",
                "slug": "kinghome-kud100-import-regression", "description": "", "price": 5000,
                "metrics": {"power_cooling": 2.94},
                "specs": {
                    "type": "полупромышленный кондиционер", "indoor_type": "напольно-потолочный",
                    "includes_indoor_unit": "true", "includes_outdoor_unit": True, "indoor_units_count": "1",
                    "capacity_cooling_kw": "10", "power_cons_cooling_kw": "2.94",
                    "temp_range_heat": "-25..+24",
                },
            }

    monkeypatch.setattr("services.importer_service.async_session_maker", lambda: _SessionContext(db))
    importer = ImporterService()
    importer.parsers = [Parser()]
    url = "https://example.test/kinghome-kud100"
    product = (await importer.import_product(url))["product"]
    assert product.product_kind == "complete_split_system"
    assert product.power_cooling == 10.0
    product_id = product.id
    for _ in range(2):
        product = (await importer.import_product(url, update_existing=True))["product"]
        assert product.id == product_id
        assert product.product_kind == "complete_split_system"
        assert product.power_cooling == 10.0
    await ProductWriteService.update_product(db, product_id, {"specs": product.specs, "power_cooling": 2.94})
    assert product.product_kind == "complete_split_system"
    assert product.power_cooling == 10.0
    result = await CatalogDecisionQueryService.list_products(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        filters=CatalogDecisionFilters(product_ids=(product_id,), cooling_btu_classes=(36,), heating_min=-25),
        page=1, limit=20, sort="recommended", direction="asc",
    )
    assert [item["id"] for item in result["items"]] == [product_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_kind", ["other", "accessory", "indoor_unit", "complete_split_system"])
async def test_reimport_preserves_explicit_legacy_or_manager_kind(db, monkeypatch, saved_kind):
    url = "https://example.test/manual-kind"
    product = Product(title="Manual product", slug="manual-kind", price=1000, product_kind=saved_kind, source_url=url)
    db.add(product)
    await db.commit()

    class Parser:
        def supports(self, url):
            return True

        async def parse(self, url):
            return {"title": product.title, "slug": product.slug, "description": "", "price": 1000,
                    "specs": {"type": "полупромышленный кондиционер", "includes_indoor_unit": True,
                              "includes_outdoor_unit": True, "indoor_units_count": 1}}

    monkeypatch.setattr("services.importer_service.async_session_maker", lambda: _SessionContext(db))
    importer = ImporterService()
    importer.parsers = [Parser()]
    await importer.import_product(url, update_existing=True)
    assert product.product_kind == saved_kind


@pytest.mark.asyncio
async def test_tcl_conflicting_primary_power_is_corrected_on_create_update_duplicate(db):
    payload = {"title": "TCL TCC-60CHRA/U3-L regression", "price": 10000, "power_cooling": 5.69,
               "specs": {"type": "сплит-система", "capacity_cooling_kw": "16.12", "power_cons_cooling_kw": "5.69"}}
    created = await ProductWriteService.create_product(db, payload)
    product = await db.get(Product, created["id"])
    assert product.power_cooling == 16.12
    assert product.product_kind == "complete_split_system"
    product.power_cooling = 5.69
    await db.commit()
    await ProductWriteService.update_product(db, product.id, {"specs": product.specs, "power_cooling": 5.69})
    assert product.power_cooling == 16.12
    duplicate = await ProductWriteService.duplicate_product(db, product.id, {"power_cooling": 5.69})
    copied = await db.get(Product, duplicate["id"])
    assert copied.power_cooling == 16.12
    assert copied.specs["power_cons_cooling_kw"] == "5.69"


@pytest.mark.asyncio
async def test_full_manager_save_derives_unknown_kind_and_respects_explicit_manual_other(db):
    product = Product(title="Legacy KINGHOME", slug="legacy-kinghome-save", price=5000, product_kind="unknown")
    db.add(product)
    await db.commit()
    specs = {"type": "полупромышленный кондиционер", "includes_indoor_unit": True,
             "includes_outdoor_unit": True, "indoor_units_count": 1, "capacity_cooling_kw": "10"}
    await ProductWriteService.update_product(db, product.id, {"specs": specs, "product_kind": "unknown"})
    assert product.product_kind == "complete_split_system"
    assert product.power_cooling == 10
    await ProductWriteService.update_product(db, product.id, {"specs": specs, "product_kind": "other"})
    assert product.product_kind == "other"
