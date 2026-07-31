import pytest

from core.config import settings
from models import Installer, StaffUser, TenantMembership


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
