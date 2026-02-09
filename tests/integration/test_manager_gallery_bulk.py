import os

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.config import settings
from models import Product, ProductImage


def _make_product(idx: int) -> Product:
    return Product(
        title=f"P{idx}",
        slug=f"p-{idx}",
        price=1000 + idx,
        area=20,
        specs={},
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
async def test_delete_shared_image_keeps_file_until_last_reference(async_client: AsyncClient, db):
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
    assert not os.path.exists(path)
