from datetime import datetime, timedelta, timezone

import pytest

from core.config import settings
from models import Product


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _product(
    *,
    title: str,
    slug: str,
    product_kind: str = "complete_split_system",
    is_published: bool = True,
    price: int = 2000,
    main_image: str | None = "/media/products/item.webp",
    specs: dict | None = None,
) -> Product:
    return Product(
        title=title,
        slug=slug,
        product_kind=product_kind,
        is_published=is_published,
        price=price,
        main_image=main_image,
        specs=specs if specs is not None else {"area_m2": 25},
    )


@pytest.mark.asyncio
async def test_manager_collection_preview_matches_public_placement(async_client, db):
    headers = await _auth_headers(async_client)
    valid = _product(title="Ready Split", slug="ready-split")
    indoor = _product(
        title="Indoor Unit",
        slug="indoor-unit",
        product_kind="indoor_unit",
    )
    hidden = _product(
        title="Hidden Split",
        slug="hidden-split",
        is_published=False,
    )
    db.add_all([valid, indoor, hidden])
    await db.commit()

    create = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Homepage master choice",
            "public_title": "Выбор мастера",
            "public_description": "Проверенные готовые системы.",
            "status": "published",
            "min_items": 1,
            "max_items": 6,
        },
    )
    assert create.status_code == 200, create.text
    collection = create.json()

    items = await async_client.put(
        f"/api/manager/product-collections/{collection['id']}/items",
        headers=headers,
        json={
            "items": [
                {"product_id": valid.id, "editorial_note": "Основная модель"},
                {"product_id": indoor.id},
                {"product_id": hidden.id},
            ]
        },
    )
    assert items.status_code == 200, items.text
    assert [item["product_id"] for item in items.json()["items"]] == [
        valid.id,
        indoor.id,
        hidden.id,
    ]

    placement = await async_client.put(
        f"/api/manager/product-collections/{collection['id']}/placements",
        headers=headers,
        json={
            "placements": [
                {
                    "surface_key": "home",
                    "slot_key": "featured_products",
                    "position": 2,
                    "is_enabled": True,
                }
            ]
        },
    )
    assert placement.status_code == 200, placement.text

    preview = await async_client.get(
        f"/api/manager/product-collections/{collection['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert [item["product"]["slug"] for item in preview_payload["items"]] == [
        "ready-split"
    ]
    excluded = {
        item["product_id"]: item["reason_codes"]
        for item in preview_payload["excluded_items"]
    }
    assert excluded[indoor.id] == ["unsupported_product_kind"]
    assert excluded[hidden.id] == ["not_published"]
    assert preview_payload["below_min_items"] is False

    public = await async_client.get(
        "/api/v1/content/placements/home/featured_products/collections"
    )
    assert public.status_code == 200, public.text
    payload = public.json()
    assert payload["surface"] == "home"
    assert payload["slot"] == "featured_products"
    assert len(payload["collections"]) == 1
    public_collection = payload["collections"][0]
    assert public_collection["slug"] == collection["slug"]
    assert public_collection["position"] == 2
    assert public_collection["items"] == preview_payload["items"]
    product = public_collection["items"][0]["product"]
    assert product["product_kind"] == "complete_split_system"
    assert product["public_stock_state"] == "out_of_stock"


@pytest.mark.asyncio
async def test_public_collection_respects_schedule_minimum_and_fallback(async_client, db):
    headers = await _auth_headers(async_client)
    primary_invalid = _product(
        title="Panel",
        slug="panel",
        product_kind="panel",
    )
    fallback_product = _product(
        title="Fallback Split",
        slug="fallback-split",
    )
    db.add_all([primary_invalid, fallback_product])
    await db.commit()

    fallback = (
        await async_client.post(
            "/api/manager/product-collections",
            headers=headers,
            json={
                "internal_name": "Fallback",
                "public_title": "Резерв",
                "status": "published",
                "min_items": 1,
                "max_items": 4,
            },
        )
    ).json()
    await async_client.put(
        f"/api/manager/product-collections/{fallback['id']}/items",
        headers=headers,
        json={"items": [{"product_id": fallback_product.id}]},
    )

    primary = (
        await async_client.post(
            "/api/manager/product-collections",
            headers=headers,
            json={
                "internal_name": "Primary",
                "public_title": "Основная",
                "status": "published",
                "min_items": 1,
                "max_items": 4,
                "fallback_collection_id": fallback["id"],
            },
        )
    ).json()
    await async_client.put(
        f"/api/manager/product-collections/{primary['id']}/items",
        headers=headers,
        json={"items": [{"product_id": primary_invalid.id}]},
    )
    await async_client.put(
        f"/api/manager/product-collections/{primary['id']}/placements",
        headers=headers,
        json={
            "placements": [
                {
                    "surface_key": "home",
                    "slot_key": "featured_products",
                    "position": 0,
                    "is_enabled": True,
                }
            ]
        },
    )

    public = await async_client.get(
        "/api/v1/content/placements/home/featured_products/collections"
    )
    assert public.status_code == 200, public.text
    collection = public.json()["collections"][0]
    assert collection["slug"] == primary["slug"]
    assert collection["items"][0]["selection_source"] == "fallback"
    assert collection["items"][0]["product"]["slug"] == "fallback-split"

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    update = await async_client.patch(
        f"/api/manager/product-collections/{primary['id']}",
        headers=headers,
        json={"starts_at": future},
    )
    assert update.status_code == 200, update.text
    hidden = await async_client.get(
        "/api/v1/content/placements/home/featured_products/collections"
    )
    assert hidden.status_code == 200
    assert hidden.json()["collections"] == []


@pytest.mark.asyncio
async def test_collection_duplicate_archive_and_validation(async_client, db):
    headers = await _auth_headers(async_client)
    product = _product(title="Split", slug="split")
    db.add(product)
    await db.commit()

    created = (
        await async_client.post(
            "/api/manager/product-collections",
            headers=headers,
            json={
                "internal_name": "Original",
                "public_title": "Оригинал",
                "min_items": 1,
                "max_items": 2,
            },
        )
    ).json()
    await async_client.put(
        f"/api/manager/product-collections/{created['id']}/items",
        headers=headers,
        json={"items": [{"product_id": product.id}]},
    )

    duplicate = await async_client.post(
        f"/api/manager/product-collections/{created['id']}/duplicate",
        headers=headers,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "draft"
    assert duplicate.json()["slug"] != created["slug"]
    assert duplicate.json()["placements"] == []
    assert duplicate.json()["items"][0]["product_id"] == product.id

    invalid_self_fallback = await async_client.patch(
        f"/api/manager/product-collections/{created['id']}",
        headers=headers,
        json={"fallback_collection_id": created["id"]},
    )
    assert invalid_self_fallback.status_code == 400

    archived = await async_client.post(
        f"/api/manager/product-collections/{created['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    async_client.cookies.clear()
    unauthenticated = await async_client.get("/api/manager/product-collections")
    assert unauthenticated.status_code == 401
