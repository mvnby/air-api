import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.config import settings
from models import Product


BASE = "/api/manager/catalog-management"


async def _platform_owner_headers(async_client) -> dict[str, str]:
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _products(db, count: int = 2) -> list[Product]:
    products = [
        Product(
            title=f"Bulk integration {index}",
            slug=f"bulk-integration-{index}",
            price=1_000 + index,
            is_published=True,
        )
        for index in range(1, count + 1)
    ]
    db.add_all(products)
    await db.commit()
    return products


async def _preview(async_client: AsyncClient, headers: dict[str, str], product_ids: list[int]):
    response = await async_client.post(
        f"{BASE}/bulk/preview",
        headers=headers,
        json={
            "product_ids": product_ids,
            "change": {"kind": "publication", "is_published": False},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_bulk_preview_does_not_persist_postgres(async_client: AsyncClient, db):
    products = await _products(db)
    product_ids = [int(product.id) for product in products]
    headers = await _platform_owner_headers(async_client)

    preview = await _preview(async_client, headers, product_ids)

    assert preview["changed_count"] == 2
    assert [item["before"] for item in preview["items"]] == [
        {"is_published": True},
        {"is_published": True},
    ]
    assert [item["after"] for item in preview["items"]] == [
        {"is_published": False},
        {"is_published": False},
    ]
    db.expire_all()
    persisted = list(
        (
            await db.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
            )
        ).scalars()
    )
    assert [product.is_published for product in persisted] == [True, True]


@pytest.mark.asyncio
async def test_bulk_apply_updates_all_previewed_products_postgres(async_client: AsyncClient, db):
    products = await _products(db)
    product_ids = [int(product.id) for product in products]
    headers = await _platform_owner_headers(async_client)
    preview = await _preview(async_client, headers, product_ids)

    applied = await async_client.post(
        f"{BASE}/bulk/apply",
        headers=headers,
        json={"token": preview["token"]},
    )

    assert applied.status_code == 200, applied.text
    assert applied.json() == {
        "updated": 2,
        "product_ids": product_ids,
    }
    db.expire_all()
    persisted = list(
        (
            await db.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
            )
        ).scalars()
    )
    assert [product.is_published for product in persisted] == [False, False]


@pytest.mark.asyncio
async def test_bulk_apply_rejects_stale_token_without_partial_write_postgres(async_client: AsyncClient, db):
    products = await _products(db)
    headers = await _platform_owner_headers(async_client)
    product_ids = [int(product.id) for product in products]
    preview = await _preview(async_client, headers, product_ids)

    changed_elsewhere = await db.get(Product, product_ids[1])
    assert changed_elsewhere is not None
    changed_elsewhere.is_published = False
    db.add(changed_elsewhere)
    await db.commit()

    applied = await async_client.post(
        f"{BASE}/bulk/apply",
        headers=headers,
        json={"token": preview["token"]},
    )

    assert applied.status_code == 409, applied.text
    db.expire_all()
    persisted = list(
        (
            await db.execute(
                select(Product).where(Product.id.in_(product_ids)).order_by(Product.id)
            )
        ).scalars()
    )
    # The first product was not staged before the stale snapshot aborted apply.
    assert [product.is_published for product in persisted] == [True, False]
