from datetime import datetime, timedelta, timezone

import pytest

from core.config import settings
from sqlmodel import select

from models import (
    IntegrationOutboxEvent,
    Product,
    StorefrontCatalogRevision,
    TenantAuditEvent,
)
from services.tenant_scope_service import SystemTenantScopeResolver


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
async def test_published_collection_can_replace_existing_children(async_client, db):
    headers = await _auth_headers(async_client)
    product = _product(title="Publish-safe split", slug="publish-safe-split")
    db.add(product)
    await db.commit()

    create = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Publish-safe collection",
            "public_title": "Надёжная публикация",
            "status": "draft",
            "min_items": 1,
            "max_items": 6,
        },
    )
    assert create.status_code == 200, create.text
    collection_id = create.json()["id"]
    items_payload = {"items": [{"product_id": product.id}]}
    placements_payload = {
        "placements": [
            {
                "surface_key": "home",
                "slot_key": "publish_safe",
                "position": 1,
                "is_enabled": True,
            }
        ]
    }

    first_items = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/items",
        headers=headers,
        json=items_payload,
    )
    assert first_items.status_code == 200, first_items.text
    first_placements = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/placements",
        headers=headers,
        json=placements_payload,
    )
    assert first_placements.status_code == 200, first_placements.text

    publish = await async_client.patch(
        f"/api/manager/product-collections/{collection_id}",
        headers=headers,
        json={"status": "published"},
    )
    assert publish.status_code == 200, publish.text

    replaced_items = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/items",
        headers=headers,
        json=items_payload,
    )
    assert replaced_items.status_code == 200, replaced_items.text
    assert [item["product_id"] for item in replaced_items.json()["items"]] == [product.id]

    replaced_placements = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/placements",
        headers=headers,
        json=placements_payload,
    )
    assert replaced_placements.status_code == 200, replaced_placements.text
    assert len(replaced_placements.json()["placements"]) == 1


@pytest.mark.asyncio
async def test_collection_commands_stage_audit_revision_and_outbox_atomically(
    async_client,
    db,
):
    headers = await _auth_headers(async_client)
    product = _product(title="Audited split", slug="audited-split")
    db.add(product)
    await db.commit()
    scope = await SystemTenantScopeResolver.resolve(db)

    created = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={"internal_name": "Audited", "public_title": "Audited"},
    )
    assert created.status_code == 200, created.text
    collection_id = created.json()["id"]
    scheduled = await async_client.patch(
        f"/api/manager/product-collections/{collection_id}",
        headers=headers,
        json={
            "starts_at": "2026-09-01T09:00:00+03:00",
            "ends_at": "2026-09-30T18:00:00+03:00",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    scheduled_placement = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/placements",
        headers=headers,
        json={
            "placements": [
                {
                    "surface_key": "home",
                    "slot_key": "scheduled",
                    "position": 0,
                    "is_enabled": True,
                    "starts_at": "2026-09-02T09:00:00+03:00",
                    "ends_at": "2026-09-29T18:00:00+03:00",
                }
            ]
        },
    )
    assert scheduled_placement.status_code == 200, scheduled_placement.text
    replaced = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/items",
        headers=headers,
        json={"items": [{"product_id": product.id}]},
    )
    assert replaced.status_code == 200, replaced.text

    audits = list(
        (
            await db.execute(
                select(TenantAuditEvent)
                .where(
                    TenantAuditEvent.tenant_id == scope.tenant_id,
                    TenantAuditEvent.storefront_id == scope.storefront_id,
                    TenantAuditEvent.entity_type == "product_collection",
                    TenantAuditEvent.entity_id == collection_id,
                )
                .order_by(TenantAuditEvent.id.asc())
            )
        ).scalars().all()
    )
    assert [row.action for row in audits] == [
        "product_collection.created",
        "product_collection.updated",
        "product_collection.placements_reordered",
        "product_collection.items_reordered",
    ]
    update_audit = audits[1].change_set
    assert isinstance(update_audit["starts_at"]["after"], str)
    assert isinstance(update_audit["ends_at"]["after"], str)
    placement_audit = audits[2].change_set
    placement_after = placement_audit["placements"]["after"][0]
    assert isinstance(placement_after["starts_at"], str)
    assert isinstance(placement_after["ends_at"], str)
    revision = await db.get(
        StorefrontCatalogRevision,
        (scope.tenant_id, scope.storefront_id),
    )
    assert revision is not None and revision.revision >= 4
    outbox = list(
        (
            await db.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == "catalog.cache_invalidation.requested.v1"
                )
            )
        ).scalars().all()
    )
    assert len(outbox) >= 4

    before_audits = len(audits)
    before_revision = revision.revision
    rejected = await async_client.put(
        f"/api/manager/product-collections/{collection_id}/items",
        headers=headers,
        json={"items": [{"product_id": 2_147_483_647}]},
    )
    assert rejected.status_code == 404
    current_audits = list(
        (
            await db.execute(
                select(TenantAuditEvent).where(
                    TenantAuditEvent.entity_type == "product_collection",
                    TenantAuditEvent.entity_id == collection_id,
                )
            )
        ).scalars().all()
    )
    await db.refresh(revision)
    assert len(current_audits) == before_audits
    assert revision.revision == before_revision


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


@pytest.mark.asyncio
async def test_hybrid_collection_pins_then_fills_by_typed_rules(async_client, db):
    headers = await _auth_headers(async_client)
    pinned = _product(
        title="Pinned premium",
        slug="pinned-premium",
        price=3000,
        specs={"area_m2": 35, "__filter_noise_min": 18},
    )
    automatic = _product(
        title="Automatic quiet",
        slug="automatic-quiet",
        price=1200,
        specs={"area_m2": 25, "__filter_noise_min": 19},
    )
    automatic_second = _product(
        title="Automatic quiet second",
        slug="automatic-quiet-second",
        price=1300,
        specs={"area_m2": 30, "__filter_noise_min": 20},
    )
    too_loud = _product(
        title="Too loud",
        slug="too-loud",
        price=1000,
        specs={"area_m2": 25, "__filter_noise_min": 31},
    )
    component = _product(
        title="Indoor candidate",
        slug="indoor-candidate",
        product_kind="indoor_unit",
        price=900,
        specs={"area_m2": 25, "__filter_noise_min": 18},
    )
    for product in (pinned, automatic, automatic_second, too_loud, component):
        product.is_inverter = True
    db.add_all([pinned, automatic, automatic_second, too_loud, component])
    await db.commit()

    created = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Hybrid",
            "public_title": "Тихие модели",
            "status": "published",
            "mode": "hybrid",
            "sort_mode": "price_asc",
            "min_items": 3,
            "max_items": 3,
            "rule_config": {
                "product_kinds": ["complete_split_system"],
                "max_price": 1500,
                "max_noise_min_db": 20,
                "is_inverter": True,
            },
        },
    )
    assert created.status_code == 200, created.text
    collection = created.json()
    items = await async_client.put(
        f"/api/manager/product-collections/{collection['id']}/items",
        headers=headers,
        json={
            "items": [
                {"product_id": component.id, "is_pinned": True},
                {"product_id": pinned.id, "is_pinned": True},
                {"product_id": automatic.id, "is_pinned": False},
            ]
        },
    )
    assert items.status_code == 200, items.text

    preview = await async_client.get(
        f"/api/manager/product-collections/{collection['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert [
        (item["selection_source"], item["product"]["slug"])
        for item in payload["items"]
    ] == [
        ("manual", "pinned-premium"),
        ("automatic", "automatic-quiet"),
        ("automatic", "automatic-quiet-second"),
    ]
    exclusions = {
        item["product_id"]: item["reason_codes"]
        for item in payload["excluded_items"]
    }
    assert exclusions[component.id] == ["unsupported_product_kind"]
    assert payload["below_min_items"] is False


@pytest.mark.asyncio
async def test_automatic_collection_requires_rules_and_duplicate_keeps_them(async_client):
    headers = await _auth_headers(async_client)
    options = await async_client.get(
        "/api/manager/product-collections/rule-options",
        headers=headers,
    )
    assert options.status_code == 200, options.text
    assert set(options.json()) == {"brands", "series", "features"}

    invalid = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Unsafe automatic",
            "public_title": "Unsafe",
            "mode": "automatic",
        },
    )
    assert invalid.status_code == 400

    invalid_range = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Invalid range",
            "public_title": "Invalid range",
            "mode": "automatic",
            "rule_config": {
                "product_kinds": ["complete_split_system"],
                "min_price": 2000,
                "max_price": 1000,
            },
        },
    )
    assert invalid_range.status_code == 422

    created = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Automatic",
            "public_title": "Автоматическая",
            "mode": "automatic",
            "sort_mode": "area_desc",
            "rule_config": {
                "product_kinds": ["complete_split_system"],
                "max_area_m2": 35,
            },
        },
    )
    assert created.status_code == 200, created.text
    duplicate = await async_client.post(
        f"/api/manager/product-collections/{created.json()['id']}/duplicate",
        headers=headers,
    )
    assert duplicate.status_code == 200, duplicate.text
    payload = duplicate.json()
    assert payload["mode"] == "automatic"
    assert payload["sort_mode"] == "area_desc"
    assert payload["rule_config"]["max_area_m2"] == 35


@pytest.mark.asyncio
async def test_system_collection_preserves_internal_stock_rules(async_client):
    headers = await _auth_headers(async_client)
    created = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Canonical stock rule",
            "public_title": "Canonical stock rule",
            "mode": "automatic",
            "rule_config": {"public_stock_states": ["out_of_stock"]},
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["rule_config"]["public_stock_states"] == ["out_of_stock"]

    updated = await async_client.patch(
        f"/api/manager/product-collections/{created.json()['id']}",
        headers=headers,
        json={"rule_config": {"public_stock_states": ["supplier_stock"]}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["rule_config"]["public_stock_states"] == [
        "supplier_stock"
    ]
