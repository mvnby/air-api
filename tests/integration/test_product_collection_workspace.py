from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlmodel import select

from crud.product_collection import ProductCollectionDAO
from models import IntegrationOutboxEvent, TenantAuditEvent
from services.manager_product_collection_service import ManagerProductCollectionService
from services.product_collection_invalidation import ProductCollectionInvalidationService
from services.tenant_scope_service import SystemTenantScopeResolver
from tests.integration.test_product_collections_api import _auth_headers, _product
from tests.integration.test_product_collection_tenant_isolation_postgres import _seed_two_scopes


@pytest.mark.asyncio
async def test_workspace_publishes_all_parts_and_preserves_placement_specific_display(async_client, db):
    headers = await _auth_headers(async_client)
    products = [_product(title=f"Workspace {i}", slug=f"workspace-{i}") for i in range(3)]
    db.add_all(products)
    await db.commit()
    created = await async_client.post("/api/manager/product-collections", headers=headers, json={"internal_name": "Workspace", "public_title": "Before"})
    assert created.status_code == 200, created.text
    collection_id = created.json()["id"]
    payload = {
        "collection": {"public_title": "After", "status": "published", "min_items": 3},
        "items": [{"product_id": product.id} for product in products],
        "placements": [
            {"surface_key": "home", "slot_key": "featured_products"},
            {"surface_key": "home", "slot_key": "after_featured", "display_mode": "grid", "item_limit": 1, "grid_columns": 4},
        ],
    }
    saved = await async_client.put(f"/api/manager/product-collections/{collection_id}/workspace", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "published"
    assert len(saved.json()["items"]) == 3
    for slot, mode, count in [("featured_products", "carousel", 3), ("after_featured", "grid", 1)]:
        public = await async_client.get(f"/api/v1/content/placements/home/{slot}/collections")
        assert public.status_code == 200, public.text
        row = public.json()["collections"][0]
        assert row["display_mode"] == mode
        assert len(row["items"]) == count
        preview = await async_client.get(f"/api/manager/product-collections/{collection_id}/preview", headers=headers, params={"surface": "home", "slot": slot})
        assert preview.status_code == 200, preview.text
        assert preview.json()["items"] == row["items"]
        assert preview.json()["below_min_items"] is False
    audits = (await db.execute(select(TenantAuditEvent).where(TenantAuditEvent.entity_id == collection_id, TenantAuditEvent.action == "product_collection.workspace_saved"))).scalars().all()
    assert len(audits) == 1
    assert set(audits[0].change_set) >= {"status", "public_title", "items", "placements"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["placements", "outbox"])
async def test_workspace_rolls_back_metadata_children_and_audit_on_late_failure(db, monkeypatch, failure_stage):
    scope = await SystemTenantScopeResolver.resolve(db)
    product = _product(title="Rollback", slug="workspace-rollback")
    db.add(product)
    await db.commit()
    actor = {"tenant_scope": scope, "actor_username": "test", "actor_staff_user_id": None}
    collection = await ManagerProductCollectionService.create_collection(db, {"internal_name": "Before", "public_title": "Before", "status": "published"}, **actor)
    collection_id = collection["id"]
    await ManagerProductCollectionService.replace_items(db, collection_id, [{"product_id": product.id}], **actor)
    await ManagerProductCollectionService.replace_placements(db, collection_id, [{"surface_key": "home", "slot_key": "featured_products"}], **actor)
    before = await ManagerProductCollectionService.get_collection(db, collection_id, tenant_scope=scope)
    audit_count = len((await db.execute(select(TenantAuditEvent))).scalars().all())
    outbox_count = len((await db.execute(select(IntegrationOutboxEvent))).scalars().all())
    if failure_stage == "placements":
        monkeypatch.setattr(ProductCollectionDAO, "replace_placements", AsyncMock(side_effect=RuntimeError("injected placement failure")))
    else:
        monkeypatch.setattr(ProductCollectionInvalidationService, "stage", AsyncMock(side_effect=RuntimeError("injected outbox failure")))
    with pytest.raises(RuntimeError, match="injected"):
        await ManagerProductCollectionService.save_workspace(db, collection_id, {"public_title": "Wrong", "status": "draft"}, items=[], placements=[], **actor)
    after = await ManagerProductCollectionService.get_collection(db, collection_id, tenant_scope=scope)
    assert after == before
    assert len((await db.execute(select(TenantAuditEvent))).scalars().all()) == audit_count
    assert len((await db.execute(select(IntegrationOutboxEvent))).scalars().all()) == outbox_count


@pytest.mark.asyncio
async def test_workspace_rejects_other_tenant_collection_product_and_fallback(db):
    scopes, products, collections = await _seed_two_scopes(db)
    first_id, other_id = [int(row.id) for row in collections]
    own_product_id, other_product_id = [int(row.id) for row in products]
    actor = {"tenant_scope": scopes[0], "actor_username": "test", "actor_staff_user_id": None}
    for collection_id, fields, items in [
        (other_id, {}, []),
        (first_id, {"public_title": "Wrong"}, [{"product_id": other_product_id}]),
        (first_id, {"fallback_collection_id": other_id}, [{"product_id": own_product_id}]),
    ]:
        with pytest.raises(HTTPException) as error:
            await ManagerProductCollectionService.save_workspace(db, collection_id, fields, items=items, placements=[], **actor)
        assert error.value.status_code == 404
    unchanged = await ManagerProductCollectionService.get_collection(db, first_id, tenant_scope=scopes[0])
    assert unchanged["public_title"] == "Featured 0"
    assert [row["product_id"] for row in unchanged["items"]] == [own_product_id]
    assert len(unchanged["placements"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"items": [{"product_id": 2_147_483_647}]},
    {"placements": [{"surface_key": "Home", "slot_key": "same"}, {"surface_key": "home", "slot_key": "same"}]},
    {"placements": [{"surface_key": "invalid/key", "slot_key": "same"}]},
    {"placements": [{"surface_key": "home", "slot_key": "same", "display_mode": "grid", "rotation_mode": "daily"}]},
    {"collection": {"status": "published", "min_items": None}},
])
async def test_workspace_rejected_input_keeps_published_metadata_and_children(async_client, db, changes):
    headers = await _auth_headers(async_client)
    created = await async_client.post("/api/manager/product-collections", headers=headers, json={"internal_name": "Before", "public_title": "Before", "status": "published"})
    collection_id = created.json()["id"]
    payload = {"collection": {"public_title": "Wrong", "status": "draft"}, "items": [], "placements": [], **changes}
    rejected = await async_client.put(f"/api/manager/product-collections/{collection_id}/workspace", headers=headers, json=payload)
    assert rejected.status_code in {400, 404, 422}, rejected.text
    current = await async_client.get(f"/api/manager/product-collections/{collection_id}", headers=headers)
    assert current.json() == created.json()


@pytest.mark.asyncio
async def test_display_migration_preserves_legacy_placements_with_defaults(db, monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    scopes, _, collections = await _seed_two_scopes(db)
    collection_id = int(collections[0].id)
    other_collection_id = int(collections[1].id)
    await db.execute(text(
        "UPDATE product_collection_placement SET surface_key = 'home', slot_key = 'featured_products' "
        "WHERE collection_id = :id"
    ), {"id": collection_id})
    migration_path = Path(__file__).parents[2] / "alembic/versions/e61d4e5f6a7_add_collection_placement_display.py"
    spec = importlib.util.spec_from_file_location("placement_display_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db.connection()

    def round_trip(sync_connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(sync_connection)))
        migration.downgrade()
        migration.upgrade()

    await connection.run_sync(round_trip)
    row = (await db.execute(text("SELECT display_mode, item_limit, grid_columns, rotation_mode FROM product_collection_placement WHERE collection_id = :id"), {"id": collection_id})).one()
    assert tuple(row) == ("grid", None, 4, "none")
    other = (await db.execute(text("SELECT display_mode, item_limit, grid_columns, rotation_mode FROM product_collection_placement WHERE collection_id = :id"), {"id": other_collection_id})).one()
    assert tuple(other) == ("carousel", None, 3, "none")


@pytest.mark.asyncio
async def test_daily_slot_selects_one_eligible_collection_after_fallback(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from services import product_collection_resolver as resolver_module
    from services import manager_product_collection_service as manager_module
    from services.product_collection_resolver import ProductCollectionResolver

    scope = await SystemTenantScopeResolver.resolve(db)
    products = [_product(title=f"Daily {i}", slug=f"daily-{i}") for i in range(2)]
    db.add_all(products)
    await db.commit()
    actor = {"tenant_scope": scope, "actor_username": "test", "actor_staff_user_id": None}
    fallback = await ManagerProductCollectionService.create_collection(db, {"internal_name": "Fallback", "public_title": "Fallback", "status": "published"}, **actor)
    await ManagerProductCollectionService.replace_items(db, fallback["id"], [{"product_id": row.id} for row in products], **actor)
    slugs = []
    collection_ids = {}
    for index in range(3):
        created = await ManagerProductCollectionService.create_collection(db, {"internal_name": f"Daily {index}", "public_title": f"Daily {index}"}, **actor)
        payload = {"status": "published", "min_items": 2}
        if index == 0:
            payload["fallback_collection_id"] = fallback["id"]
        saved = await ManagerProductCollectionService.save_workspace(
            db, created["id"], payload,
            items=[{"product_id": row.id} for row in products] if index == 1 else [],
            placements=[{"surface_key": "home", "slot_key": "product_of_day", "position": index, "display_mode": "single", "rotation_mode": "daily"}], **actor,
        )
        slugs.append(saved["slug"])
        collection_ids[saved["slug"]] = saved["id"]
    day = datetime(2026, 9, 16, tzinfo=timezone.utc)
    seen = {slug: set() for slug in slugs[:2]}
    for offset in range(4):
        now = day + timedelta(days=offset)
        monkeypatch.setattr(resolver_module, "utc_now", lambda: now)
        monkeypatch.setattr(manager_module, "utc_now", lambda: now)
        result = await ProductCollectionResolver.resolve_placement(db, surface_key="home", slot_key="product_of_day", tenant_scope=scope)
        assert len(result["collections"]) == 1
        row = result["collections"][0]
        assert row["slug"] == slugs[now.date().toordinal() % 2]
        assert len(row["items"]) == 1
        selected_product_id = row["items"][0]["product"].id
        assert selected_product_id == products[(now.date().toordinal() // 2) % 2].id
        seen[row["slug"]].add(selected_product_id)
        preview = await ManagerProductCollectionService.preview(
            db, collection_id=collection_ids[row["slug"]], surface_key="home",
            slot_key="product_of_day", tenant_scope=scope,
        )
        assert preview["items"] == row["items"]
        assert preview["below_min_items"] is False
        nonselected_slug = slugs[(now.date().toordinal() + 1) % 2]
        independent = await ManagerProductCollectionService.preview(
            db, collection_id=collection_ids[nonselected_slug], surface_key="home",
            slot_key="product_of_day", tenant_scope=scope,
        )
        assert independent["items"][0]["product"].id == products[now.date().toordinal() % 2].id
    assert all(ids == {product.id for product in products} for ids in seen.values())
