import pytest

from core.command_actor import CommandActor
from models import Brand, Product, ProductSeries, Storefront, Tenant, TenantCatalogGrant, TenantOffer
from models.catalog_accessory import SeriesAccessoryLink
from models.catalog_document import CatalogDocument
from models.tenancy import TenantScope
from schemas_connector_catalog import CatalogProductInput, CatalogSelectionInput
from services.connector_catalog_selection_service import ConnectorCatalogSelectionService


@pytest.mark.asyncio
@pytest.mark.parametrize("partner", [False, True])
async def test_connector_catalog_detail_public_inherited_materials_and_scoped_accessories(db, partner):
    brand = Brand(title="Reference Brand", slug="reference-brand", official_url="https://brand.example.com/")
    db.add(brand)
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="FG Reference", slug="fg-reference", source_url="https://supplier.example.com/private-source")
    db.add(series)
    await db.flush()
    product = Product(
        title="FG Reference 09", slug="fg-reference-09", brand_id=brand.id, series_id=series.id,
        product_kind="complete_split_system", price=1000, power_cooling=2.6,
        specs={"area_m2": 25, "indoor_type": "настенный", "wifi_state": "ready"},
    )
    accessory = Product(title="FG Wi-Fi", slug="fg-wifi-module", product_kind="accessory", price=80, specs={"accessory_type": "wifi_module"})
    hidden_accessory = Product(title="FG Invisible Wi-Fi", slug="fg-invisible-module", product_kind="accessory", price=81, is_published=False)
    db.add_all([product, accessory, hidden_accessory])
    await db.flush()
    db.add_all([
        CatalogDocument(product_id=product.id, title="Own certificate", url="https://docs.example.com/certificate.pdf", kind="certificate", source_url="https://supplier.example.com/secret-provenance"),
        CatalogDocument(series_id=series.id, title="Series operation", url="https://docs.example.com/operation.pdf", kind="operation", language="ru", year=2026),
        CatalogDocument(brand_id=brand.id, title="Brand catalog", url="https://docs.example.com/catalog.pdf", kind="catalog"),
        CatalogDocument(series_id=series.id, title="TOP SECRET INTERNAL MANUAL", url="https://docs.example.com/internal.pdf", visibility="internal", kind="service"),
        CatalogDocument(series_id=series.id, title="Do not inherit", url="https://docs.example.com/no-inheritance.pdf", inherit_to_products=False),
        SeriesAccessoryLink(series_id=series.id, accessory_product_id=accessory.id),
        SeriesAccessoryLink(series_id=series.id, accessory_product_id=hidden_accessory.id, sort_order=1),
    ])
    scope = TenantScope(tenant_id=1, storefront_id=1, is_canonical_storefront=True)
    if partner:
        tenant = Tenant(slug="reference-partner", display_name="Reference Partner")
        db.add(tenant)
        await db.flush()
        storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Reference Storefront", status="active")
        db.add(storefront)
        await db.flush()
        grant = TenantCatalogGrant(tenant_id=tenant.id, storefront_id=storefront.id, status="active", created_by_username="test", updated_by_username="test")
        db.add(grant)
        await db.flush()
        db.add_all([
            TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id, catalog_grant_id=grant.id, product_id=product.id, price=1234, is_published=True, created_by_username="test", updated_by_username="test"),
            TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id, catalog_grant_id=grant.id, product_id=accessory.id, price=345, old_price=400, is_published=True, created_by_username="test", updated_by_username="test"),
        ])
        scope = TenantScope(tenant_id=tenant.id, storefront_id=storefront.id, is_canonical_storefront=False)
    await db.flush()
    actor = CommandActor(staff_user_id=1, username="reference-reader", tenant_scope=scope, channel="connector")
    detail = await ConnectorCatalogSelectionService.get_product(db, actor, CatalogProductInput(product_id=product.id))
    assert detail.unit_price_byn == (1234 if partner else 1000)
    assert [item.title for item in detail.documents] == ["Own certificate", "Series operation", "Brand catalog"]
    assert [item.origin_type for item in detail.documents] == ["product", "series", "brand"]
    assert [item.inherited for item in detail.documents] == [False, True, True]
    assert [item.product_id for item in detail.accessories] == [accessory.id]
    assert detail.accessories[0].price == (345 if partner else 80)
    assert detail.accessories[0].suggested_for_purchase is True
    serialized = detail.model_dump_json()
    for prohibited in ("TOP SECRET", "internal.pdf", "no-inheritance", "secret-provenance", "private-source", "official_url", "source_url", "supplier_id", "min_cost_byn", "vitebsk_qty"):
        assert prohibited not in serialized
    selection = await ConnectorCatalogSelectionService.select(db, actor, CatalogSelectionInput(cooling_btu_class=9))
    assert selection.options
    assert "documents" not in selection.options[0].product.model_dump()
    assert "accessories" not in selection.options[0].product.model_dump()
