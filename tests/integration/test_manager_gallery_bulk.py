import os

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.config import settings
from models import (
    Brand,
    IntegrationOutboxEvent,
    Product,
    ProductImage,
    ProductImageVariant,
    ProductSeries,
)
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.catalog_revision_service import CatalogRevisionService


def _make_product(idx: int) -> Product:
    return Product(
        title=f"P{idx}",
        slug=f"p-{idx}",
        price=1000 + idx,
        specs={"area_m2": 20},
    )


async def _auth_headers(async_client: AsyncClient) -> dict:
    login_payload = {
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD,
    }
    login_resp = await async_client.post("/login/access-token", data=login_payload)
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_common_gallery_images_returns_only_intersection(async_client: AsyncClient, db):
    p1 = _make_product(1)
    p2 = _make_product(2)
    p3 = _make_product(3)
    db.add_all([p1, p2, p3])
    await db.commit()
    for p in [p1, p2, p3]:
        await db.refresh(p)

    db.add_all([
        ProductImage(product_id=p1.id, url="/media/products/shared/common.webp", is_installation_photo=False),
        ProductImage(product_id=p2.id, url="/media/products/shared/common.webp", is_installation_photo=False),
        ProductImage(product_id=p3.id, url="/media/products/shared/common.webp", is_installation_photo=False),
        ProductImage(product_id=p1.id, url="/media/products/shared/partial.webp", is_installation_photo=False),
        ProductImage(product_id=p2.id, url="/media/products/shared/partial.webp", is_installation_photo=False),
        ProductImage(product_id=p1.id, url="/media/products/shared/install.webp", is_installation_photo=True),
        ProductImage(product_id=p2.id, url="/media/products/shared/install.webp", is_installation_photo=True),
        ProductImage(product_id=p3.id, url="/media/products/shared/install.webp", is_installation_photo=True),
    ])
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/gallery/common-images",
        params=[("product_ids", p1.id), ("product_ids", p2.id), ("product_ids", p3.id)],
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["url"] == "/media/products/shared/common.webp"


@pytest.mark.asyncio
async def test_bulk_delete_common_removes_only_selected_products(async_client: AsyncClient, db):
    p1 = _make_product(11)
    p2 = _make_product(12)
    p3 = _make_product(13)
    db.add_all([p1, p2, p3])
    await db.commit()
    for p in [p1, p2, p3]:
        await db.refresh(p)
    p3_id = p3.id

    common_url = "/media/products/shared/to-delete.webp"
    db.add_all([
        ProductImage(product_id=p1.id, url=common_url, is_installation_photo=False),
        ProductImage(product_id=p2.id, url=common_url, is_installation_photo=False),
        ProductImage(product_id=p3.id, url=common_url, is_installation_photo=False),
        ProductImage(product_id=p1.id, url="/media/products/shared/only-p1.webp", is_installation_photo=False),
    ])
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/gallery/bulk-delete-common",
        json={
            "product_ids": [p1.id, p2.id],
            "urls": [common_url],
            "exclude_installation": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    db.expire_all()
    left = (
        await db.execute(select(ProductImage).where(ProductImage.url == common_url))
    ).scalars().all()
    assert len(left) == 1
    assert left[0].product_id == p3_id


@pytest.mark.asyncio
async def test_bulk_delete_common_removes_variants_only_for_deleted_links(async_client: AsyncClient, db):
    p1 = _make_product(31)
    p2 = _make_product(32)
    p3 = _make_product(33)
    db.add_all([p1, p2, p3])
    await db.commit()
    for p in [p1, p2, p3]:
        await db.refresh(p)

    common_url = "/media/products/shared/with-variants.webp"
    img1 = ProductImage(product_id=p1.id, url=common_url, is_installation_photo=False)
    img2 = ProductImage(product_id=p2.id, url=common_url, is_installation_photo=False)
    img3 = ProductImage(product_id=p3.id, url=common_url, is_installation_photo=False)
    db.add_all([img1, img2, img3])
    await db.commit()
    for img in [img1, img2, img3]:
        await db.refresh(img)
    p3_id = p3.id
    img3_id = img3.id

    db.add_all([
        ProductImageVariant(
            product_image_id=img1.id,
            variant_type="card",
            url="/media/products/shared/with-variants-p1-card.webp",
            processing_status="ready",
        ),
        ProductImageVariant(
            product_image_id=img2.id,
            variant_type="card",
            url="/media/products/shared/with-variants-p2-card.webp",
            processing_status="ready",
        ),
        ProductImageVariant(
            product_image_id=img3.id,
            variant_type="card",
            url="/media/products/shared/with-variants-p3-card.webp",
            processing_status="ready",
        ),
    ])
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/gallery/bulk-delete-common",
        json={
            "product_ids": [p1.id, p2.id],
            "urls": [common_url],
            "exclude_installation": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    db.expire_all()

    remaining_images = (
        await db.execute(select(ProductImage).where(ProductImage.url == common_url))
    ).scalars().all()
    assert [image.product_id for image in remaining_images] == [p3_id]

    remaining_variants = (
        await db.execute(select(ProductImageVariant).order_by(ProductImageVariant.id))
    ).scalars().all()
    assert len(remaining_variants) == 1
    assert remaining_variants[0].product_image_id == img3_id


@pytest.mark.asyncio
async def test_series_gallery_can_be_added_to_all_series_products(async_client: AsyncClient, db):
    brand = Brand(title="Series gallery brand", slug="series-gallery-brand")
    db.add(brand)
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Shared gallery series",
        slug="shared-gallery-series",
    )
    db.add(series)
    await db.flush()
    first = _make_product(41)
    first.brand_id = brand.id
    first.series_id = series.id
    second = _make_product(42)
    second.brand_id = brand.id
    second.series_id = series.id
    outside = _make_product(43)
    db.add_all([first, second, outside])
    await db.commit()

    urls = [
        "/media/library/original/series-gallery-1.webp",
        "/media/library/original/series-gallery-2.webp",
    ]
    headers = await _auth_headers(async_client)
    endpoint = f"/api/manager/brands/{brand.id}/series/{series.id}/gallery/apply-to-products"
    before_revision = await CatalogRevisionService.get_current(db)
    response = await async_client.post(endpoint, json={"source_urls": urls}, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["products_count"] == 2
    assert response.json()["added_links"] == 4
    await db.refresh(series)
    assert series.gallery_images == urls

    linked_rows = (
        await db.execute(select(ProductImage).where(ProductImage.url.in_(urls)).order_by(ProductImage.id))
    ).scalars().all()
    assert {row.product_id for row in linked_rows} == {first.id, second.id}
    after_first_revision = await CatalogRevisionService.get_current(db)

    repeated = await async_client.post(endpoint, json={"source_urls": urls}, headers=headers)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["added_links"] == 0
    assert repeated.json()["skipped_existing"] == 4
    after_repeated_revision = await CatalogRevisionService.get_current(db)
    assert after_first_revision["revision"] == before_revision["revision"] + 1
    assert after_repeated_revision["revision"] == after_first_revision["revision"]

    events = (
        await db.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            )
        )
    ).scalars().all()
    gallery_events = [
        event
        for event in events
        if event.payload.get("reason") == "brand_series_gallery_apply"
    ]
    assert len(gallery_events) == 1


@pytest.mark.asyncio
async def test_delete_shared_image_defers_file_cleanup_after_last_reference(
    async_client: AsyncClient,
    db,
):
    p1 = _make_product(21)
    p2 = _make_product(22)
    db.add_all([p1, p2])
    await db.commit()
    for p in [p1, p2]:
        await db.refresh(p)

    url = "/media/products/shared/test-safe-delete.webp"
    path = "media/products/shared/test-safe-delete.webp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"test")

    img1 = ProductImage(product_id=p1.id, url=url, is_installation_photo=False)
    img2 = ProductImage(product_id=p2.id, url=url, is_installation_photo=False)
    db.add_all([img1, img2])
    await db.commit()
    await db.refresh(img1)
    await db.refresh(img2)

    headers = await _auth_headers(async_client)

    r1 = await async_client.delete(f"/api/manager/gallery/{img1.id}", headers=headers)
    assert r1.status_code == 200
    assert os.path.exists(path)

    r2 = await async_client.delete(f"/api/manager/gallery/{img2.id}", headers=headers)
    assert r2.status_code == 200
    assert os.path.exists(path)
    os.remove(path)
