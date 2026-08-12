import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import settings
from models.product import Product
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource
from services.supplier_offer_mapping_service import (
    SupplierOfferMappingConflictError,
    SupplierOfferMappingService,
)
from services.supplier_mapping_service import SupplierCatalogService


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_mapping_catalog(db):
    supplier = Supplier(name="Mapping Supplier", code="mapping-supplier")
    product = Product(title="Target MDSAG-09", slug="target-mdsag-09", price=1000)
    other_product = Product(title="Other Product", slug="other-product", price=1100)
    db.add_all([supplier, product, other_product])
    await db.flush()
    source = SupplierPriceSource(supplier_id=supplier.id, sheet_name="Prices")
    db.add(source)
    await db.flush()
    offers = [
        SupplierOffer(
            supplier_id=supplier.id,
            source_id=source.id,
            external_id="FREE-MDSAG-09",
            title_raw="Free MDSAG-09HRFN8",
            title_normalized="free mdsag-09hrfn8",
            model_tokens=["MDSAG-09HRFN8"],
            qty=3,
            wholesale_value=500,
            wholesale_currency="USD",
            source_url="https://example.test/free",
        ),
        SupplierOffer(
            supplier_id=supplier.id,
            source_id=source.id,
            external_id="CURRENT-09",
            title_raw="Current 09",
        ),
        SupplierOffer(
            supplier_id=supplier.id,
            source_id=source.id,
            external_id="CONFLICT-09",
            title_raw="Conflict 09",
        ),
        SupplierOffer(
            supplier_id=supplier.id,
            source_id=source.id,
            external_id="INACTIVE-09",
            title_raw="Inactive 09",
            is_active=False,
        ),
    ]
    db.add_all(offers)
    await db.flush()
    current = ProductSupplierMapping(
        product_id=product.id,
        supplier_id=supplier.id,
        external_id="CURRENT-09",
        mapped_by="first-user",
    )
    conflict = ProductSupplierMapping(
        product_id=other_product.id,
        supplier_id=supplier.id,
        external_id="CONFLICT-09",
        mapped_by="other-user",
    )
    db.add_all([current, conflict])
    await db.commit()
    return supplier, source, product, other_product, offers, current, conflict


@pytest.mark.asyncio
async def test_candidate_search_reports_mapping_states_and_details(async_client, db):
    headers = await _auth_headers(async_client)
    supplier, source, product, other_product, offers, current, conflict = await _seed_mapping_catalog(db)
    response = await async_client.get(
        f"/api/manager/products/{product.id}/supplier-offer-candidates",
        headers=headers,
        params={
            "supplier_id": supplier.id,
            "source_id": source.id,
            "include_inactive": "true",
            "limit": 2,
            "page": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["meta"] == {"total": 4, "page": 1, "limit": 2, "pages": 2}

    search = await async_client.get(
        f"/api/manager/products/{product.id}/supplier-offer-candidates",
        headers=headers,
        params={"supplier_id": supplier.id, "q": "MDSAG-09HRFN8"},
    )
    assert search.status_code == 200
    item = search.json()["items"][0]
    assert item["offer_id"] == offers[0].id
    assert item["status"] == "free"
    assert item["source_url"] == "https://example.test/free"
    assert item["wholesale_value"] == 500.0
    assert item["wholesale_currency"] == "USD"

    all_items = await async_client.get(
        f"/api/manager/products/{product.id}/supplier-offer-candidates",
        headers=headers,
        params={"supplier_id": supplier.id, "include_inactive": "true", "limit": 100},
    )
    by_external_id = {item["external_id"]: item for item in all_items.json()["items"]}
    assert by_external_id["CURRENT-09"]["status"] == "current"
    assert by_external_id["CURRENT-09"]["mapped_by"] == "first-user"
    assert by_external_id["CONFLICT-09"]["status"] == "conflict"
    assert by_external_id["CONFLICT-09"]["mapped_product_id"] == other_product.id
    assert by_external_id["CONFLICT-09"]["mapped_product_title"] == other_product.title
    assert by_external_id["INACTIVE-09"]["status"] == "inactive"


@pytest.mark.asyncio
async def test_put_mapping_is_idempotent_rebinds_with_optimistic_guard_and_reactivates(async_client, db):
    headers = await _auth_headers(async_client)
    supplier, source, product, other_product, offers, current, conflict = await _seed_mapping_catalog(db)
    product_id = product.id
    other_product_id = other_product.id
    offer_ids = [offer.id for offer in offers]
    conflict_id = conflict.id

    first = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[0]}/mapping",
        headers=headers,
        json={"product_id": product_id},
    )
    assert first.status_code == 200
    first_data = first.json()
    repeated = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[0]}/mapping",
        headers=headers,
        json={"product_id": product_id},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first_data["id"]
    assert repeated.json()["mapped_at"] == first_data["mapped_at"]

    no_replace = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[2]}/mapping",
        headers=headers,
        json={"product_id": product_id},
    )
    assert no_replace.status_code == 409
    assert f"mapping_id={conflict_id}" in no_replace.json()["detail"]["message"]

    stale_replace = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[2]}/mapping",
        headers=headers,
        json={
            "product_id": product_id,
            "replace_existing": True,
            "expected_mapping_id": conflict_id,
            "expected_product_id": product_id,
        },
    )
    assert stale_replace.status_code == 409

    replaced = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[2]}/mapping",
        headers=headers,
        json={
            "product_id": product_id,
            "replace_existing": True,
            "expected_mapping_id": conflict_id,
            "expected_product_id": other_product_id,
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["id"] == conflict_id
    assert replaced.json()["product_id"] == product_id

    mapping = await db.get(ProductSupplierMapping, first_data["id"])
    mapping.is_active = False
    await db.commit()
    reactivated = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[0]}/mapping",
        headers=headers,
        json={"product_id": other_product_id},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["id"] == first_data["id"]
    assert reactivated.json()["product_id"] == other_product_id
    assert reactivated.json()["is_active"] is True

    inactive = await async_client.put(
        f"/api/manager/supplier-offers/{offer_ids[3]}/mapping",
        headers=headers,
        json={"product_id": product_id},
    )
    assert inactive.status_code == 400
    assert "Inactive supplier offer" in inactive.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_concurrent_mapping_assignments_serialize_on_offer(db_engine):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        supplier = Supplier(name="Concurrent Supplier", code="concurrent-supplier")
        product_a = Product(title="Concurrent A", slug="concurrent-a", price=100)
        product_b = Product(title="Concurrent B", slug="concurrent-b", price=100)
        seed.add_all([supplier, product_a, product_b])
        await seed.flush()
        offer = SupplierOffer(supplier_id=supplier.id, external_id="CONCURRENT-1")
        seed.add(offer)
        await seed.commit()
        offer_id = offer.id
        product_ids = [product_a.id, product_b.id]

    async def assign(product_id: int):
        async with factory() as session:
            return await SupplierOfferMappingService.put_mapping(
                session,
                offer_id=offer_id,
                product_id=product_id,
                replace_existing=False,
                expected_mapping_id=None,
                expected_product_id=None,
                mapped_by="concurrent-test",
            )

    results = await asyncio.gather(*(assign(product_id) for product_id in product_ids), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, SupplierOfferMappingConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_delete_source_only_deactivates_its_own_offers_and_mappings(db):
    supplier = Supplier(name="Multi-source Supplier", code="multi-source-supplier")
    product_a = Product(title="Source A product", slug="source-a-product", price=100)
    product_b = Product(title="Source B product", slug="source-b-product", price=100)
    db.add_all([supplier, product_a, product_b])
    await db.flush()
    source_a = SupplierPriceSource(supplier_id=supplier.id, sheet_name="A")
    source_b = SupplierPriceSource(supplier_id=supplier.id, sheet_name="B")
    db.add_all([source_a, source_b])
    await db.flush()
    offer_a = SupplierOffer(supplier_id=supplier.id, source_id=source_a.id, external_id="SOURCE-A")
    offer_b = SupplierOffer(supplier_id=supplier.id, source_id=source_b.id, external_id="SOURCE-B")
    db.add_all([offer_a, offer_b])
    await db.flush()
    mapping_a = ProductSupplierMapping(
        product_id=product_a.id,
        supplier_id=supplier.id,
        external_id=offer_a.external_id,
    )
    mapping_b = ProductSupplierMapping(
        product_id=product_b.id,
        supplier_id=supplier.id,
        external_id=offer_b.external_id,
    )
    db.add_all([mapping_a, mapping_b])
    await db.commit()

    assert await SupplierCatalogService.delete_source(db, source_a.id) is True
    await db.refresh(offer_a)
    await db.refresh(offer_b)
    await db.refresh(mapping_a)
    await db.refresh(mapping_b)
    assert offer_a.source_id is None
    assert offer_a.is_active is False
    assert mapping_a.is_active is False
    assert offer_b.source_id == source_b.id
    assert offer_b.is_active is True
    assert mapping_b.is_active is True


@pytest.mark.asyncio
async def test_unmapped_search_uses_server_pagination(async_client, db):
    headers = await _auth_headers(async_client)
    supplier = Supplier(name="Search Supplier", code="search-supplier")
    db.add(supplier)
    await db.flush()
    db.add_all(
        [
            SupplierOffer(
                supplier_id=supplier.id,
                external_id="SEARCH-ONE",
                title_raw="Plain title",
                model_tokens=["MODEL-ONE"],
            ),
            SupplierOffer(
                supplier_id=supplier.id,
                external_id="SEARCH-TWO",
                title_raw="Special title",
                model_tokens=["MODEL-TWO"],
            ),
            SupplierOffer(
                supplier_id=supplier.id,
                external_id="IGNORED",
                title_raw="Different item",
            ),
        ]
    )
    await db.commit()

    response = await async_client.get(
        "/api/manager/supplier-offers/unmapped",
        headers=headers,
        params={"supplier_id": supplier.id, "q": "MODEL", "page": 2, "limit": 1},
    )
    assert response.status_code == 200
    assert response.json()["meta"] == {"total": 2, "page": 2, "limit": 1, "pages": 2}
    assert len(response.json()["items"]) == 1

    escaped_wildcard = await async_client.get(
        "/api/manager/supplier-offers/unmapped",
        headers=headers,
        params={"supplier_id": supplier.id, "q": "%"},
    )
    assert escaped_wildcard.status_code == 200
    assert escaped_wildcard.json()["meta"]["total"] == 0
