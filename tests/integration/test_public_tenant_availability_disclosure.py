from __future__ import annotations

import json
import time
from decimal import Decimal

import pytest

from core.config import settings
from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureSeriesLink,
    Product,
    ProductAttachment,
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
    ProductLocalStock,
    ProductSeries,
    ProductSupplierMapping,
    Storefront,
    StorefrontDomain,
    Supplier,
    SupplierOffer,
    SupplierPriceSource,
    Tenant,
    TenantCatalogGrant,
    TenantOffer,
)
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)


_KEY_ID = "test-polotsk-public"
_SECRET = "test-polotsk-public-secret-at-least-32-bytes"
_FOREIGN_KEY_ID = "test-foreign-public"
_FOREIGN_SECRET = "test-foreign-public-secret-at-least-32-bytes"
_POLOTSK_HOST = "polotsk.mvn.by"
_FOREIGN_HOST = "foreign-polotsk.test"
_PROHIBITED_PRODUCT_KEYS = {
    "vitebsk_qty",
    "minsk_qty",
    "public_stock_state",
    "source_url",
    "supplier_id",
    "supplier_name",
    "min_cost_byn",
    "recommended_price_byn",
    "margin_abs_preview",
    "margin_pct_preview",
    "wholesale_value",
    "wholesale_currency",
}


def _configure_signing(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON",
        json.dumps(
            {
                "keys": {
                    _KEY_ID: {
                        "secret": _SECRET,
                        "host_roles": {_POLOTSK_HOST: "primary"},
                    },
                    _FOREIGN_KEY_ID: {
                        "secret": _FOREIGN_SECRET,
                        "host_roles": {_FOREIGN_HOST: "primary"},
                    },
                }
            }
        ),
    )
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
        "",
    )
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        "",
    )


def _signed_headers(path_and_query: str, hostname: str) -> dict[str, str]:
    timestamp = int(time.time())
    key_id, secret = (
        (_KEY_ID, _SECRET)
        if hostname == _POLOTSK_HOST
        else (_FOREIGN_KEY_ID, _FOREIGN_SECRET)
    )
    return {
        "Host": "test",
        "X-MVN-Storefront-Key-Id": key_id,
        "X-MVN-Storefront-Host": hostname,
        "X-MVN-Storefront-Timestamp": str(timestamp),
        "X-MVN-Storefront-Signature": StorefrontContextSignatureService.sign(
            secret=secret,
            timestamp=timestamp,
            method="GET",
            path_and_query=path_and_query,
            api_hostname="test",
            storefront_hostname=hostname,
            body_sha256=StorefrontContextSignatureService.EMPTY_BODY_SHA256,
            idempotency_key_sha256="",
        ),
    }


def _assert_tenant_neutral_product(payload: dict, *, expected_status: str) -> None:
    assert payload["availability_status"] == expected_status
    assert _PROHIBITED_PRODUCT_KEYS.isdisjoint(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "TOP SECRET SUPPLIER" not in serialized
    assert "supplier.example" not in serialized


async def _seed_storefront(
    db,
    *,
    tenant_slug: str,
    storefront_slug: str,
    hostname: str,
):
    tenant = Tenant(
        slug=tenant_slug,
        display_name=tenant_slug.title(),
        status="active",
        is_system=False,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug=storefront_slug,
        display_name=tenant_slug.title(),
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname=hostname,
            status="active",
            is_primary=True,
        )
    )
    await db.flush()
    return tenant, storefront


@pytest.mark.asyncio
async def test_signed_polotsk_uses_one_deep_tenant_neutral_projection(
    async_client,
    db,
    monkeypatch,
):
    polotsk_tenant, polotsk_storefront = await _seed_storefront(
        db,
        tenant_slug="polotsk",
        storefront_slug="main",
        hostname=_POLOTSK_HOST,
    )
    foreign_tenant, foreign_storefront = await _seed_storefront(
        db,
        tenant_slug="foreign-polotsk",
        storefront_slug="main",
        hostname=_FOREIGN_HOST,
    )
    category = FeatureCategory(slug="tenant-safe", name="Tenant safe")
    brand = Brand(
        title="Tenant Safe Brand",
        slug="tenant-safe-brand",
        is_published=True,
    )
    db.add_all([category, brand])
    await db.flush()
    feature = Feature(
        category_id=int(category.id),
        brand_id=int(brand.id),
        scope_type="brand",
        name="Private provenance feature",
        slug="private-provenance-feature",
        source_url="https://supplier.example/private-feature.pdf",
        image_url="/media/features/public.webp",
        is_active=True,
    )
    series = ProductSeries(
        brand_id=int(brand.id),
        title="Tenant Safe Series",
        slug="tenant-safe-series",
        source_url="https://supplier.example/private-series.pdf",
        is_published=True,
    )
    db.add_all([feature, series])
    await db.flush()
    db.add_all(
        [
            FeatureBrandLink(
                brand_id=int(brand.id),
                feature_id=int(feature.id),
            ),
            FeatureSeriesLink(
                series_id=int(series.id),
                feature_id=int(feature.id),
            ),
        ]
    )
    local_product = Product(
        title="Polotsk Available Now",
        slug="polotsk-available-now",
        brand_id=int(brand.id),
        series_id=int(series.id),
        price=9000,
        product_kind="complete_split_system",
        specs={"area_m2": 25},
        source_url="https://supplier.example/private-product-local",
        is_published=True,
    )
    supplier_product = Product(
        title="Polotsk Supplier Availability Marker",
        slug="polotsk-supplier-availability",
        brand_id=int(brand.id),
        series_id=int(series.id),
        price=9100,
        product_kind="complete_split_system",
        specs={"area_m2": 35},
        main_image="/media/products/polotsk-supplier.webp",
        source_url="https://supplier.example/private-product-supplier",
        is_published=True,
    )
    out_product = Product(
        title="Polotsk Out Of Stock",
        slug="polotsk-out-of-stock",
        price=9200,
        product_kind="complete_split_system",
        specs={"area_m2": 50},
        is_published=True,
    )
    foreign_product = Product(
        title="Foreign Tenant Product",
        slug="foreign-tenant-product",
        price=9300,
        product_kind="complete_split_system",
        specs={"area_m2": 60},
        is_published=True,
    )
    db.add_all([local_product, supplier_product, out_product, foreign_product])
    await db.flush()
    db.add(
        ProductAttachment(
            product_id=int(supplier_product.id),
            kind="manual",
            title="Public installation manual",
            url="https://manufacturer.example/public-manual.pdf",
            source="TOP SECRET SUPPLIER portal",
        )
    )
    grant = TenantCatalogGrant(
        tenant_id=int(polotsk_tenant.id),
        storefront_id=int(polotsk_storefront.id),
        status="active",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    db.add(grant)
    await db.flush()
    db.add_all(
        [
            TenantOffer(
                tenant_id=int(polotsk_tenant.id),
                storefront_id=int(polotsk_storefront.id),
                product_id=int(product.id),
                catalog_grant_id=int(grant.id),
                price=price,
                price_source="inherited_master",
                status="active",
                is_published=True,
                created_by_username="system:test",
                updated_by_username="system:test",
            )
            for product, price in (
                (local_product, 3000),
                (supplier_product, 4000),
                (out_product, 5000),
            )
        ]
    )
    db.add(
        TenantOffer(
            tenant_id=int(foreign_tenant.id),
            storefront_id=int(foreign_storefront.id),
            product_id=int(foreign_product.id),
            price=6000,
            status="active",
            is_published=True,
            created_by_username="system:test",
            updated_by_username="system:test",
        )
    )
    supplier = Supplier(name="TOP SECRET SUPPLIER", code="top-secret-supplier")
    db.add(supplier)
    await db.flush()
    source = SupplierPriceSource(
        supplier_id=int(supplier.id),
        city_bucket="minsk",
        is_active=True,
    )
    db.add(source)
    await db.flush()
    offer = SupplierOffer(
        supplier_id=int(supplier.id),
        source_id=int(source.id),
        external_id="SECRET-SKU",
        source_url="https://supplier.example/private-offer",
        qty=6,
        qty_raw="6",
        wholesale_value=Decimal("1234.56"),
        wholesale_currency="BYN",
        is_active=True,
    )
    db.add(offer)
    await db.flush()
    db.add_all(
        [
            ProductSupplierMapping(
                product_id=int(supplier_product.id),
                supplier_id=int(supplier.id),
                external_id=offer.external_id,
            ),
            ProductLocalStock(
                product_id=int(local_product.id),
                warehouse_code="vitebsk",
                qty=7,
                updated_by="test",
            ),
        ]
    )
    collection = ProductCollection(
        tenant_id=int(polotsk_tenant.id),
        storefront_id=int(polotsk_storefront.id),
        slug="polotsk-safe-collection",
        internal_name="Polotsk safe collection",
        public_title="Polotsk safe collection",
        status="published",
        min_items=1,
        max_items=4,
    )
    db.add(collection)
    await db.flush()
    db.add_all(
        [
            ProductCollectionItem(
                tenant_id=int(polotsk_tenant.id),
                storefront_id=int(polotsk_storefront.id),
                collection_id=int(collection.id),
                product_id=int(supplier_product.id),
                position=0,
            ),
            ProductCollectionPlacement(
                tenant_id=int(polotsk_tenant.id),
                storefront_id=int(polotsk_storefront.id),
                surface_key="home",
                slot_key="tenant_safe",
                collection_id=int(collection.id),
                position=0,
                is_enabled=True,
            ),
        ]
    )
    await db.commit()
    _configure_signing(monkeypatch)

    catalog_path = "/api/v1/products?limit=20"
    catalog = await async_client.get(
        catalog_path,
        headers=_signed_headers(catalog_path, _POLOTSK_HOST),
    )
    assert catalog.status_code == 200, catalog.text
    by_slug = {item["slug"]: item for item in catalog.json()["items"]}
    assert set(by_slug) == {
        local_product.slug,
        supplier_product.slug,
        out_product.slug,
    }
    _assert_tenant_neutral_product(
        by_slug[local_product.slug],
        expected_status="in_stock_now",
    )
    _assert_tenant_neutral_product(
        by_slug[supplier_product.slug],
        expected_status="available_2_3_days",
    )
    assert by_slug[supplier_product.slug]["delivery_min_days"] == 2
    assert by_slug[supplier_product.slug]["delivery_max_days"] == 3
    _assert_tenant_neutral_product(
        by_slug[out_product.slug],
        expected_status="out_of_stock",
    )

    detail_path = f"/api/v1/products/{supplier_product.slug}"
    detail = await async_client.get(
        detail_path,
        headers=_signed_headers(detail_path, _POLOTSK_HOST),
    )
    assert detail.status_code == 200, detail.text
    _assert_tenant_neutral_product(
        detail.json(),
        expected_status="available_2_3_days",
    )
    assert "source_url" not in detail.json()["series"]
    assert "source_url" not in detail.json()["series"]["brand_features"][0]
    assert "source" not in detail.json()["manuals"][0]

    search_path = "/api/products/search?q=Supplier%20Availability%20Marker"
    search = await async_client.get(
        search_path,
        headers=_signed_headers(search_path, _POLOTSK_HOST),
    )
    assert search.status_code == 200, search.text
    _assert_tenant_neutral_product(
        search.json()["items"][0],
        expected_status="available_2_3_days",
    )

    featured_path = "/api/v1/products/vitebsk-featured"
    featured = await async_client.get(
        featured_path,
        headers=_signed_headers(featured_path, _POLOTSK_HOST),
    )
    assert featured.status_code == 200, featured.text
    assert featured.json() == []

    collection_path = "/api/v1/content/placements/home/tenant_safe/collections"
    collection_response = await async_client.get(
        collection_path,
        headers=_signed_headers(collection_path, _POLOTSK_HOST),
    )
    assert collection_response.status_code == 200, collection_response.text
    collection_product = collection_response.json()["collections"][0]["items"][0]["product"]
    _assert_tenant_neutral_product(
        collection_product,
        expected_status="available_2_3_days",
    )
    assert "source_url" not in collection_product["series"]
    assert "source_url" not in collection_product["series"]["brand_features"][0]

    series_path = "/api/v1/content/brands/tenant-safe-brand/series/tenant-safe-series"
    series_response = await async_client.get(
        series_path,
        headers=_signed_headers(series_path, _POLOTSK_HOST),
    )
    assert series_response.status_code == 200, series_response.text
    assert "source_url" not in series_response.json()["series"]
    assert "source_url" not in series_response.json()["series"]["brand_features"][0]
    for product in series_response.json()["products"]:
        assert _PROHIBITED_PRODUCT_KEYS.isdisjoint(product)

    brand_path = "/api/v1/content/brands/tenant-safe-brand"
    brand_response = await async_client.get(
        brand_path,
        headers=_signed_headers(brand_path, _POLOTSK_HOST),
    )
    assert brand_response.status_code == 200, brand_response.text
    assert "source_url" not in brand_response.json()["features"][0]
    assert brand_response.json()["features"][0]["image_url"] == "/media/features/public.webp"

    foreign_catalog = await async_client.get(
        catalog_path,
        headers=_signed_headers(catalog_path, _FOREIGN_HOST),
    )
    assert foreign_catalog.status_code == 200, foreign_catalog.text
    assert [item["slug"] for item in foreign_catalog.json()["items"]] == [
        foreign_product.slug
    ]

    canonical_detail = await async_client.get(detail_path)
    assert canonical_detail.status_code == 200, canonical_detail.text
    canonical_payload = canonical_detail.json()
    assert canonical_payload["minsk_qty"] == 6
    assert canonical_payload["vitebsk_qty"] == 0
    assert canonical_payload["availability_status"] == "available_2_3_days"
    assert canonical_payload["public_stock_state"] == "supplier_stock"
    assert canonical_payload["series"]["source_url"] == (
        "https://supplier.example/private-series.pdf"
    )
    assert canonical_payload["series"]["brand_features"][0]["source_url"] == (
        "https://supplier.example/private-feature.pdf"
    )
    assert canonical_payload["manuals"][0]["source"] == "TOP SECRET SUPPLIER portal"


@pytest.mark.asyncio
async def test_polotsk_offer_and_grant_boundaries_fail_closed(
    async_client,
    db,
    monkeypatch,
):
    tenant, storefront = await _seed_storefront(
        db,
        tenant_slug="polotsk-boundaries",
        storefront_slug="main",
        hostname=_POLOTSK_HOST,
    )
    visible_null_grant = Product(
        title="Visible local tenant offer",
        slug="visible-null-grant",
        price=1000,
        is_published=True,
    )
    disabled_offer_product = Product(
        title="Disabled offer",
        slug="disabled-offer-boundary",
        price=1000,
        is_published=True,
    )
    disabled_grant_product = Product(
        title="Disabled grant",
        slug="disabled-grant-boundary",
        price=1000,
        is_published=True,
    )
    no_offer_product = Product(
        title="No offer",
        slug="no-offer-boundary",
        price=1000,
        is_published=True,
    )
    db.add_all(
        [
            visible_null_grant,
            disabled_offer_product,
            disabled_grant_product,
            no_offer_product,
        ]
    )
    await db.flush()
    disabled_grant = TenantCatalogGrant(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        status="disabled",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    db.add(disabled_grant)
    await db.flush()
    db.add_all(
        [
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(visible_null_grant.id),
                catalog_grant_id=None,
                price=1100,
                status="active",
                is_published=True,
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(disabled_offer_product.id),
                catalog_grant_id=None,
                price=1200,
                status="disabled",
                is_published=True,
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(disabled_grant_product.id),
                catalog_grant_id=int(disabled_grant.id),
                price=1300,
                price_source="inherited_master",
                status="active",
                is_published=True,
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
        ]
    )
    await db.commit()
    _configure_signing(monkeypatch)

    path = "/api/v1/products?limit=20"
    response = await async_client.get(
        path,
        headers=_signed_headers(path, _POLOTSK_HOST),
    )
    assert response.status_code == 200, response.text
    assert [item["slug"] for item in response.json()["items"]] == [
        visible_null_grant.slug
    ]
    _assert_tenant_neutral_product(
        response.json()["items"][0],
        expected_status="out_of_stock",
    )

    tampered_headers = _signed_headers(path, _FOREIGN_HOST)
    tampered_headers["X-MVN-Storefront-Host"] = _POLOTSK_HOST
    tampered = await async_client.get(path, headers=tampered_headers)
    assert tampered.status_code == 401
