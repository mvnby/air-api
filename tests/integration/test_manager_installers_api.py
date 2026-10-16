import pytest

from core.config import settings
from models import Installer, LegacyOwnerAuthState, StaffUser, TenantMembership
from sqlmodel import select


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_installers_search_uses_active_staff_users(async_client, db):
    active = Installer(name="Legacy Active", is_active=True)
    blocked = Installer(name="Legacy Blocked", is_active=True)
    inactive = Installer(name="Legacy Inactive", is_active=True)
    db.add_all([active, blocked, inactive])
    await db.flush()

    active_staff = StaffUser(
        display_name="Active Staff Installer",
        status="active",
        roles=["installer"],
        legacy_installer_id=active.id,
    )
    blocked_staff = StaffUser(
        display_name="Blocked Staff Installer",
        status="blocked",
        roles=["installer"],
        legacy_installer_id=blocked.id,
    )
    inactive_staff = StaffUser(
        display_name="Inactive Staff Installer",
        status="inactive",
        roles=["installer"],
        legacy_installer_id=inactive.id,
    )
    db.add_all([active_staff, blocked_staff, inactive_staff])
    await db.flush()
    db.add_all(
        [
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(active_staff.id),
                role="installer",
                status="active",
            ),
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(blocked_staff.id),
                role="installer",
                status="suspended",
            ),
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(inactive_staff.id),
                role="installer",
                status="disabled",
            ),
        ]
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/installers/search",
        params={"q": "Staff", "limit": 10},
        headers=headers,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items] == ["Active Staff Installer"]
    assert items[0]["id"] == active.id

    legacy_name_response = await async_client.get(
        "/api/manager/installers/search",
        params={"q": "Legacy Active", "limit": 10},
        headers=headers,
    )

    assert legacy_name_response.status_code == 200
    assert [item["name"] for item in legacy_name_response.json()["items"]] == ["Active Staff Installer"]


@pytest.mark.asyncio
async def test_manager_installers_list_keeps_blocked_historical_staff_visible(async_client, db):
    installer = Installer(name="Legacy Historical", is_active=True)
    db.add(installer)
    await db.flush()
    staff = StaffUser(
        display_name="Blocked Historical Staff",
        status="blocked",
        roles=["installer"],
        legacy_installer_id=installer.id,
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff.id),
            role="installer",
            status="suspended",
        )
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/installers",
        params={"search": "Historical"},
        headers=headers,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Blocked Historical Staff"
    assert items[0]["is_active"] is False


async def _staff_login(async_client, owner_headers, role):
    response = await async_client.post("/api/manager/staff", headers=owner_headers, json={
        "display_name": f"Installer test {role}", "primary_role": role,
        "username": f"installer-test-{role}", "password": "secret-12345",
    })
    assert response.status_code == 200
    login = await async_client.post("/login/access-token", data={
        "username": f"installer-test-{role}", "password": "secret-12345",
    })
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _assignable_owner(async_client, owner_headers):
    response = await async_client.post("/api/manager/staff", headers=owner_headers, json={
        "display_name": "Assignable company owner", "primary_role": "owner",
        "telegram_id": 808, "is_assignable_installer": True,
    })
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_crm_manager_cannot_create_or_update_installer_accounts(async_client, db):
    owner_headers = await _auth_headers(async_client)
    installer_response = await async_client.post("/api/manager/installers", headers=owner_headers,
                                                 json={"name": "Contractor"})
    assert installer_response.status_code == 200
    manager_headers = await _staff_login(async_client, owner_headers, "manager")
    response = await async_client.put(
        f"/api/manager/installers/{installer_response.json()['id']}",
        headers=manager_headers, json={"telegram_id": 909, "is_active": False},
    )
    assert response.status_code == 403
    response = await async_client.post("/api/manager/installers", headers=manager_headers,
                                       json={"name": "Unauthorized"})
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"is_active": False}, {"telegram_id": 909}])
async def test_installer_endpoint_admin_cannot_disable_or_rebind_owner(async_client, db, changes):
    owner_headers = await _auth_headers(async_client)
    owner = await _assignable_owner(async_client, owner_headers)
    admin_headers = await _staff_login(async_client, owner_headers, "admin")
    response = await async_client.put(
        f"/api/manager/installers/{owner['legacy_installer_id']}",
        headers=admin_headers, json=changes,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "staff_role_forbidden"
    staff = await db.get(StaffUser, owner["id"])
    assert staff.telegram_id == 808
    assert staff.status == "active"
    membership = (await db.execute(select(TenantMembership).where(
        TenantMembership.staff_user_id == owner["id"], TenantMembership.tenant_id == 1,
    ))).scalar_one()
    assert membership.status == "active"


@pytest.mark.asyncio
async def test_installer_endpoint_cannot_disable_last_owner(async_client, db):
    headers = await _auth_headers(async_client)
    owner = await _assignable_owner(async_client, headers)
    response = await async_client.put(
        f"/api/manager/installers/{owner['legacy_installer_id']}",
        headers=headers, json={"is_active": False},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "last_active_owner"


@pytest.mark.asyncio
async def test_installer_endpoint_keeps_legacy_owner_identity_fence(async_client, db):
    headers = await _auth_headers(async_client)
    owner = await _assignable_owner(async_client, headers)
    state = await db.get(LegacyOwnerAuthState, 1)
    state.owner_staff_user_id = owner["id"]
    await db.commit()
    response = await async_client.put(
        f"/api/manager/installers/{owner['legacy_installer_id']}",
        headers=headers, json={"telegram_id": 909},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "legacy_owner_managed"


@pytest.mark.asyncio
async def test_installer_endpoint_cannot_rebind_catalog_grantee(async_client, db):
    owner_headers = await _auth_headers(async_client)
    created = await async_client.post("/api/manager/installers", headers=owner_headers,
                                      json={"name": "Delegated contractor", "telegram_id": 707})
    assert created.status_code == 200
    staff = (await db.execute(select(StaffUser).where(
        StaffUser.legacy_installer_id == created.json()["id"],
    ))).scalar_one()
    membership = (await db.execute(select(TenantMembership).where(
        TenantMembership.staff_user_id == staff.id, TenantMembership.tenant_id == 1,
    ))).scalar_one()
    membership.permissions = ["catalog.master.edit"]
    await db.commit()
    admin_headers = await _staff_login(async_client, owner_headers, "admin")
    response = await async_client.put(
        f"/api/manager/installers/{created.json()['id']}",
        headers=admin_headers, json={"telegram_id": 909},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "catalog_grantee_identity_protected"
