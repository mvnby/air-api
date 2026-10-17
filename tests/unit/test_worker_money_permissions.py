"""Company cash delegation preserves global catalog grants and fresh authority."""

from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api_contracts.manager_access import ManagerAccessUpdate
from core.database import get_session
from core.security import AuthenticatedIdentity
from models import TenantAuditEvent, TenantMembership
from routers.manager_staff import router
from services.manager_access_service import ManagerAccessService
from services.manager_capability_service import ManagerCapabilityService
from tests.unit.test_manager_multicompany import multi_db as multi_db  # noqa: F401
from tests.unit.test_order_responsibility import auth, headers


@pytest.fixture
async def money_permission_client(multi_db):  # noqa: F811
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: multi_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield multi_db, client


async def test_cash_permission_is_company_local_audited_and_preserves_catalog(
    money_permission_client,
):
    session, client = money_permission_client
    path = "/api/manager/staff/10"
    body = {"can_manage_worker_money": True}
    assert (
        await client.patch(path, headers=headers(4, team=False), json=body)
    ).status_code == 403
    response = await client.patch(path, headers=headers(4), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["can_manage_worker_money"] is True
    member = await session.get(TenantMembership, 10)
    assert set(member.permissions) == {"catalog.master.edit", "worker.money.manage"}
    assert (await session.get(TenantMembership, 20)).permissions == []
    audit = await session.scalar(
        select(TenantAuditEvent).where(
            TenantAuditEvent.action == "staff_membership_updated"
        )
    )
    assert (
        "worker.money.manage" in audit.change_set["membership"]["after"]["permissions"]
    )
    response = await client.patch(
        path, headers=headers(4), json={"can_manage_worker_money": False}
    )
    assert response.status_code == 200
    assert response.json()["can_manage_worker_money"] is False
    assert (await session.get(TenantMembership, 10)).permissions == [
        "catalog.master.edit"
    ]


async def test_manager_cannot_grant_self_but_platform_owner_can_delegate_for_partner(
    money_permission_client,
):
    _, client = money_permission_client
    assert (
        await client.patch(
            "/api/manager/staff/10",
            headers=headers(),
            json={"can_manage_worker_money": True},
        )
    ).status_code == 403
    delegated = await client.patch(
        "/api/manager/staff/10", headers=headers(4, 2),
        json={"primary_role": "manager", "can_manage_worker_money": True},
    )
    assert delegated.status_code == 200, delegated.text
    assert delegated.json()["can_manage_worker_money"] is True
    # Support delegates to a real company member; it does not acquire that grant.
    assert "worker.money.manage" not in ManagerCapabilityService.for_auth(
        replace(auth(4, 2), role="owner", access_kind="platform_support", is_platform_owner=True))


async def test_catalog_permission_replacement_preserves_cash_delegation(multi_db):  # noqa: F811
    member = await multi_db.get(TenantMembership, 10)
    member.permissions = ["catalog.master.edit", "worker.money.manage"]
    await multi_db.commit()
    actor = AuthenticatedIdentity(
        username="root", auth_source="test", staff_user_id=4, is_platform_owner=True
    )
    result = await ManagerAccessService.update(
        multi_db,
        membership_id=10,
        payload=ManagerAccessUpdate(
            permissions=[], expected_updated_at=member.updated_at
        ),
        actor=actor,
    )
    assert result.permissions == []
    assert (await multi_db.get(TenantMembership, 10)).permissions == [
        "worker.money.manage"
    ]


def test_capabilities_follow_actual_role_and_explicit_cash_grant():
    assert "worker.money.manage" not in ManagerCapabilityService.for_auth(auth())
    assert "worker.money.manage" in ManagerCapabilityService.for_auth(
        replace(auth(), permissions=("worker.money.manage",))
    )
    assert "worker.money.manage" not in ManagerCapabilityService.for_auth(
        replace(auth(), role="installer", permissions=("worker.money.manage",))
    )
    assert "worker.money.manage" not in ManagerCapabilityService.for_auth(
        replace(auth(), role="owner", access_kind="platform_support")
    )
