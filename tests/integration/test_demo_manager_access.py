from datetime import timedelta

import pytest
from core.security import create_access_token
from models import StaffUser, Storefront, Tenant, TenantMembership
from services.staff_user_service import StaffUserService


async def _demo_owner(db):
    tenant = Tenant(slug="demo-test", display_name="Demo", demo_read_only=True)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=tenant.id, slug="main", display_name="Demo", status="active",
        is_default=True,
    )
    user = StaffUser(
        display_name="Demo", username="demo-access-test", status="active",
        roles=["owner"], primary_role="owner",
        password_hash=StaffUserService.hash_password("demo-test-password"),
    )
    db.add_all([storefront, user])
    await db.flush()
    db.add(TenantMembership(
        tenant_id=tenant.id, staff_user_id=user.id, role="owner", status="active",
    ))
    await db.commit()
    return tenant, user


def _headers(user):
    token = create_access_token({
        "sub": user.username, "staff_user_id": user.id,
        "auth_version": user.auth_version, "auth_source": "staff_password",
        # Client-supplied claims must not relax the persisted tenant policy.
        "demo_read_only": False, "is_system_tenant": True,
    }, expires_delta=timedelta(minutes=10))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_demo_login_has_read_only_owner_access_without_password_change(async_client, db):
    tenant, user = await _demo_owner(db)
    login = await async_client.post("/login/access-token", data={
        "username": user.username, "password": "demo-test-password",
    })
    assert login.status_code == 200
    me = await async_client.get("/api/manager/me")
    assert me.status_code == 200
    assert me.json()["demo_read_only"] is True
    assert me.json()["tenant_id"] == tenant.id
    assert me.json()["is_system_tenant"] is False
    assert me.json()["can_change_password"] is False
    assert "settings.manage" in me.json()["capabilities"]
    orders = await async_client.get("/api/manager/orders")
    assert orders.status_code == 200
    assert (await async_client.post("/login/logout")).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/manager/customers"),
    ("PATCH", "/api/manager/orders/9999"),
    ("DELETE", "/api/manager/orders/9999"),
    ("POST", "/api/manager/account/change-password"),
    ("GET", "/api/manager/document-drive/authorization-url"),
])
async def test_demo_mutations_fail_before_business_work(async_client, db, method, path):
    _tenant, user = await _demo_owner(db)
    response = await async_client.request(method, path, headers=_headers(user), json={})
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "demo_read_only"


@pytest.mark.asyncio
async def test_demo_cannot_bypass_policy_with_storefront_header_or_claim(async_client, db):
    tenant, user = await _demo_owner(db)
    db.add(Storefront(
        tenant_id=tenant.id, slug="other", display_name="Other", status="active",
    ))
    await db.commit()
    headers = {**_headers(user), "X-MVN-Manager-Storefront": "other"}
    response = await async_client.post("/api/manager/customers", headers=headers, json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "demo_read_only"


@pytest.mark.asyncio
async def test_demo_policy_is_refreshed_for_existing_tokens(async_client, db):
    tenant, user = await _demo_owner(db)
    headers = _headers(user)
    tenant.demo_read_only = False
    db.add(tenant)
    await db.commit()
    normal = await async_client.get("/api/manager/me", headers=headers)
    assert normal.json()["demo_read_only"] is False
    assert normal.json()["can_change_password"] is True
    tenant.demo_read_only = True
    db.add(tenant)
    await db.commit()
    demo = await async_client.get("/api/manager/me", headers=headers)
    assert demo.json()["demo_read_only"] is True
    assert demo.json()["can_change_password"] is False
