import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from models import StaffUser, TenantMembership
from models.tenancy import TenantScope
from schemas import ManagerStaffCreatePayload, ManagerStaffUpdatePayload
from services.staff_access_policy import StaffAccessPolicyError
from services.staff_user_service import StaffUserService


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_staff_crud_hides_password_hash_and_changes_password(async_client, db):
    headers = await _auth_headers(async_client)

    create_response = await async_client.post(
        "/api/manager/staff",
        json={
            "display_name": "Офис Менеджер",
            "primary_role": "manager",
            "status": "active",
            "username": "office",
            "password": "secret-12345",
            "phone": "+375291112233",
            "email": "office@example.com",
            "telegram_id": 123456,
            "telegram_username": "office_mvn",
            "is_assignable_installer": False,
        },
        headers=headers,
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["primary_role"] == "manager"
    assert created["has_password"] is True
    assert created["is_assignable_installer"] is False
    assert "password_hash" not in created

    login_response = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "secret-12345"},
    )
    assert login_response.status_code == 200

    patch_response = await async_client.patch(
        f"/api/manager/staff/{created['id']}",
        json={
            "password": "newsecret123",
            "primary_role": "owner",
            "is_assignable_installer": True,
            "default_rate": 250,
        },
        headers=headers,
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["primary_role"] == "owner"
    assert patched["is_assignable_installer"] is True
    assert patched["legacy_installer_id"] is not None

    old_login = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "secret-12345"},
    )
    assert old_login.status_code == 400

    new_login = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "newsecret123"},
    )
    assert new_login.status_code == 200

    list_response = await async_client.get("/api/manager/staff", headers=headers)
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["display_name"] == "Офис Менеджер"
    assert "password_hash" not in item


@pytest.mark.asyncio
async def test_admin_staff_api_cannot_promote_or_modify_owners(async_client, db):
    owner_headers = await _auth_headers(async_client)
    admin_response = await async_client.post("/api/manager/staff", json={
        "display_name": "Tenant admin", "primary_role": "admin",
        "username": "tenant-admin", "password": "secret-12345",
    }, headers=owner_headers)
    assert admin_response.status_code == 200
    assert admin_response.json()["primary_role"] == "admin"
    owner_response = await async_client.post("/api/manager/staff", json={
        "display_name": "Tenant owner", "primary_role": "owner",
    }, headers=owner_headers)
    assert owner_response.status_code == 200
    login = await async_client.post("/login/access-token", data={
        "username": "tenant-admin", "password": "secret-12345",
    })
    assert login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for privileged_role in ("owner", "admin"):
        response = await async_client.post("/api/manager/staff", json={
            "display_name": "Forbidden", "primary_role": privileged_role,
        }, headers=admin_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "staff_role_forbidden"
    response = await async_client.patch(
        f"/api/manager/staff/{owner_response.json()['id']}",
        json={"display_name": "Hijacked owner"}, headers=admin_headers,
    )
    assert response.status_code == 403
    editor_response = await async_client.post("/api/manager/staff", json={
        "display_name": "Editor", "primary_role": "catalog_editor",
    }, headers=admin_headers)
    assert editor_response.status_code == 200
    assert editor_response.json()["primary_role"] == "catalog_editor"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    ({"primary_role": "admin"}, {"primary_role": "admin"}),
    ({"status": "blocked"}, {"status": "inactive"}),
    ({"primary_role": "admin"}, {"status": "blocked"}),
])
async def test_concurrent_owner_changes_preserve_one_active_owner(db_engine, changes):
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        owners = [await StaffUserService.create_staff(
            session,
            ManagerStaffCreatePayload(display_name=f"Owner {index}", primary_role="owner"),
            tenant_scope=scope,
        ) for index in range(2)]

    async def change_owner(staff_id, payload):
        async with sessions() as session:
            try:
                await StaffUserService.update_staff(
                    session, staff_id, ManagerStaffUpdatePayload(**payload),
                    tenant_scope=scope, actor_role="owner", actor_staff_user_id=staff_id,
                    actor_username=f"owner-{staff_id}",
                )
                return "changed"
            except StaffAccessPolicyError as exc:
                await session.rollback()
                return exc.code

    outcomes = await asyncio.wait_for(asyncio.gather(
        *(change_owner(owner.id, payload) for owner, payload in zip(owners, changes, strict=True))
    ), timeout=15)
    assert sorted(outcomes) == ["changed", "last_active_owner"]
    async with sessions() as session:
        active_owners = list((await session.execute(
            select(TenantMembership).join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
            .where(TenantMembership.tenant_id == scope.tenant_id,
                   TenantMembership.role == "owner", TenantMembership.status == "active",
                   StaffUser.status == "active")
        )).scalars())
        assert len(active_owners) == 1
