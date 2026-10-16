"""Exercise authorization through real tokens, memberships and HTTP dependencies."""

import pytest
from sqlalchemy import select

from core.config import settings
from core.security import create_access_token
from models import LegacyOwnerAuthState, Product, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership


EDIT = "catalog.master.edit"
DELETE = "catalog.master.delete"
ACCESS_URL = "/api/manager/platform/access"


async def _staff(db, *, role="manager", system=False, permissions=()):
    tenant_id = 1
    if not system:
        tenant = Tenant(slug="access-partner", display_name="Access partner")
        db.add(tenant)
        await db.flush()
        tenant_id = tenant.id
        db.add(Storefront(tenant_id=tenant_id, slug="main", display_name="Partner", status="active", is_default=True))
    user = StaffUser(display_name="Access user", username="access-user", roles=[role], primary_role=role)
    db.add(user)
    await db.flush()
    membership = TenantMembership(tenant_id=tenant_id, staff_user_id=user.id, role=role, permissions=list(permissions))
    db.add(membership)
    await db.commit()
    return user, membership


def _headers(user, **claims):
    token = create_access_token({
        "sub": user.username, "staff_user_id": user.id,
        "auth_source": "staff_password", "auth_version": user.auth_version, **claims,
    })
    return {"Authorization": f"Bearer {token}"}


async def _owner_headers(client):
    response = await client.post("/login/access-token", data={
        "username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD,
    })
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["manager", "admin", "owner"])
async def test_system_company_membership_cannot_imply_platform_authority(async_client, db, role):
    user, membership = await _staff(db, role=role, system=True)
    headers = _headers(user, is_platform_owner=True, permissions=[EDIT, DELETE], role="owner")
    for method, path, payload in (
        ("post", "/api/manager/tags/groups", {"title": "Denied"}),
        ("post", "/api/manager/brands", {"title": "Denied"}),
        ("post", "/api/manager/products", {"title": "Denied"}),
        ("get", "/api/manager/suppliers", None),
        ("get", "/api/manager/settings", None),
        ("get", ACCESS_URL, None),
        ("patch", f"{ACCESS_URL}/{membership.id}", {"permissions": [EDIT], "expected_updated_at": membership.updated_at.isoformat()}),
    ):
        response = await async_client.request(method, path, headers=headers, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 403, (path, response.text)
    me = await async_client.get("/api/manager/me", headers=headers)
    assert me.status_code == 200
    assert not {"platform.manage", "infrastructure.manage", EDIT, DELETE}.intersection(me.json()["capabilities"])


@pytest.mark.asyncio
async def test_partner_catalog_editor_can_edit_catalog_without_crm_or_platform_access(async_client, db):
    user, _ = await _staff(db, role="catalog_editor", permissions=(EDIT,))
    headers = _headers(user)
    me = await async_client.get("/api/manager/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["capabilities"] == ["catalog.master.read", EDIT]
    brand = await async_client.post("/api/manager/brands", json={"title": "Delegated brand"}, headers=headers)
    assert brand.status_code == 200, brand.text
    tags = await async_client.post("/api/manager/tags/groups", json={"title": "Delegated tags"}, headers=headers)
    assert tags.status_code == 200, tags.text
    product = await async_client.post("/api/manager/products", json={"title": "Delegated product", "brand_id": brand.json()["id"]}, headers=headers)
    assert product.status_code == 200, product.text
    stored = (await db.execute(select(Product).where(Product.title == "Delegated product"))).scalar_one()
    product_path = f"/api/manager/products/{stored.id}"
    edited = await async_client.patch(product_path, json={"description": "Updated by collaborator"}, headers=headers)
    assert edited.status_code == 200, edited.text
    read = await async_client.get(product_path, headers=headers)
    assert read.status_code == 200, read.text
    await db.refresh(stored)
    assert stored.description == "Updated by collaborator"
    hidden = await async_client.patch(product_path, json={"is_published": False}, headers=headers)
    assert hidden.status_code == 403, hidden.text
    assert (await async_client.delete(product_path, headers=headers)).status_code == 403
    await db.refresh(stored)
    assert stored.is_published is True
    for path in ("/api/manager/brands", "/api/manager/tags/groups", "/api/manager/products/list"):
        response = await async_client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
    for path in ("/api/manager/customers", "/api/manager/staff", "/api/manager/orders", "/api/manager/suppliers", "/api/manager/settings", ACCESS_URL):
        response = await async_client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.text)
    for path, payload in (
        ("/api/manager/staff", {"display_name": "Forbidden", "primary_role": "manager"}),
        ("/api/manager/suppliers", {"name": "Forbidden supplier"}),
        ("/api/manager/settings", {"key": "forbidden", "value": "yes"}),
        ("/api/manager/products/bulk-round-price", {"product_ids": [1], "step": 10}),
    ):
        response = await async_client.post(path, json=payload, headers=headers)
        assert response.status_code == 403, (path, response.text)
    response = await async_client.delete(f"/api/manager/tags/groups/{tags.json()['id']}", headers=headers)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_company_owner_cannot_delegate_catalog_permission_to_themselves(async_client, db, role):
    user, membership = await _staff(db, role=role)
    response = await async_client.patch(f"{ACCESS_URL}/{membership.id}", headers=_headers(user), json={
        "permissions": [EDIT, DELETE], "expected_updated_at": membership.updated_at.isoformat(),
    })
    assert response.status_code == 403
    await db.refresh(membership)
    assert membership.permissions == []


@pytest.mark.asyncio
async def test_catalog_grants_revoke_live_and_deletion_is_separate(async_client, db):
    user, membership = await _staff(db, role="catalog_editor", permissions=(EDIT,))
    headers = _headers(user)
    owner_headers = await _owner_headers(async_client)
    group = await async_client.post("/api/manager/tags/groups", json={"title": "Temporary"}, headers=headers)
    assert group.status_code == 200, group.text
    path = f"/api/manager/tags/groups/{group.json()['id']}"
    assert (await async_client.delete(path, headers=headers)).status_code == 403
    granted = await async_client.patch(f"{ACCESS_URL}/{membership.id}", headers=owner_headers, json={
        "permissions": [EDIT, DELETE], "expected_updated_at": membership.updated_at.isoformat(),
    })
    assert granted.status_code == 200, granted.text
    assert (await async_client.delete(path, headers=headers)).status_code == 200
    revoked = await async_client.patch(f"{ACCESS_URL}/{membership.id}", headers=owner_headers, json={
        "permissions": [], "expected_updated_at": granted.json()["updated_at"],
    })
    assert revoked.status_code == 200, revoked.text
    denied = await async_client.post("/api/manager/tags/groups", json={"title": "Revoked"}, headers=headers)
    assert denied.status_code == 403
    me = await async_client.get("/api/manager/me", headers=headers)
    assert me.status_code == 200
    assert EDIT not in me.json()["capabilities"]


@pytest.mark.asyncio
@pytest.mark.parametrize("inactive", ["membership", "identity", "tenant"])
async def test_catalog_permission_requires_live_active_identity_and_membership(async_client, db, inactive):
    user, membership = await _staff(db, role="catalog_editor", permissions=(EDIT,))
    headers = _headers(user)
    assert (await async_client.get("/api/manager/products/list", headers=headers)).status_code == 200
    target = membership if inactive == "membership" else user if inactive == "identity" else await db.get(Tenant, membership.tenant_id)
    target.status = "inactive" if inactive == "identity" else "disabled"
    db.add(target)
    await db.commit()
    response = await async_client.get("/api/manager/products/list", headers=headers)
    assert response.status_code == (401 if inactive == "identity" else 403)


@pytest.mark.asyncio
async def test_owner_delegation_is_audited_validated_and_rejects_stale_updates(async_client, db):
    _, membership = await _staff(db, role="catalog_editor")
    membership_id, tenant_id = membership.id, membership.tenant_id
    headers = await _owner_headers(async_client)
    listing = await async_client.get(ACCESS_URL, headers=headers)
    assert listing.status_code == 200, listing.text
    item = next(item for item in listing.json()["items"] if item["membership_id"] == membership_id)
    assert item["permissions"] == []
    assert not {"password_hash", "password", "email", "phone", "telegram_id"}.intersection(item)
    assert (await async_client.get(f"{ACCESS_URL}?limit=101", headers=headers)).status_code == 422
    for permissions in ([DELETE], [EDIT, EDIT], ["platform.manage"], ["infrastructure.manage"]):
        response = await async_client.patch(f"{ACCESS_URL}/{membership_id}", headers=headers, json={
            "permissions": permissions, "expected_updated_at": item["updated_at"],
        })
        assert response.status_code == 422, response.text
    update = await async_client.patch(f"{ACCESS_URL}/{membership_id}", headers=headers, json={
        "permissions": [EDIT], "expected_updated_at": item["updated_at"],
    })
    assert update.status_code == 200, update.text
    stale = await async_client.patch(f"{ACCESS_URL}/{membership_id}", headers=headers, json={
        "permissions": [], "expected_updated_at": item["updated_at"],
    })
    assert stale.status_code == 409, stale.text
    noop = await async_client.patch(f"{ACCESS_URL}/{membership_id}", headers=headers, json={
        "permissions": [EDIT], "expected_updated_at": update.json()["updated_at"],
    })
    assert noop.status_code == 200
    assert noop.json()["updated_at"] == update.json()["updated_at"]
    events = list((await db.execute(select(TenantAuditEvent).where(TenantAuditEvent.action == "staff.catalog_permissions_changed"))).scalars())
    assert len(events) == 1
    assert events[0].entity_id == membership_id
    assert events[0].tenant_id == tenant_id
    assert events[0].actor_username == settings.ADMIN_USERNAME
    assert events[0].change_set == {"permissions": {"before": [], "after": [EDIT]}}
    response = await async_client.patch(f"{ACCESS_URL}/99999", headers=headers, json={
        "permissions": [], "expected_updated_at": item["updated_at"],
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_platform_owner_is_the_live_bound_identity_and_legacy_owner_still_works(async_client, db):
    legacy_headers = await _owner_headers(async_client)
    assert (await async_client.get(ACCESS_URL, headers=legacy_headers)).status_code == 200
    user, _ = await _staff(db, role="owner", system=True)
    user.username = settings.ADMIN_USERNAME
    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode = "staff_shadow"
    state.owner_staff_user_id = user.id
    db.add_all([user, state])
    await db.commit()
    headers = _headers(user)
    assert (await async_client.get(ACCESS_URL, headers=headers)).status_code == 200
    assert (await async_client.get(ACCESS_URL, headers=legacy_headers)).status_code == 401
    me = await async_client.get("/api/manager/me", headers=headers)
    assert {"platform.manage", "infrastructure.manage", EDIT, DELETE} <= set(me.json()["capabilities"])
    state.mode = "legacy"
    db.add(state)
    await db.commit()
    assert (await async_client.get(ACCESS_URL, headers=headers)).status_code == 401
