"""Remuneration rights stay separate from cash custody and catalog editing."""

from dataclasses import replace

from models import TenantMembership
from services.manager_capability_service import ManagerCapabilityService as Caps
from tests.unit.test_order_responsibility import auth, headers
from tests.unit.test_worker_money_permissions import (  # noqa: F401
    money_permission_client as money_permission_client,
    multi_db as multi_db,
)


async def test_pay_delegation_preserves_cash_and_catalog(money_permission_client):  # noqa: F811
    session, client = money_permission_client
    member = await session.get(TenantMembership, 10)
    member.permissions = ["catalog.master.edit", "worker.money.manage"]
    await session.commit()
    path = "/api/manager/staff/10"
    granted = await client.patch(
        path, headers=headers(4), json={"can_manage_worker_pay": True}
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["can_manage_worker_pay"] is True
    assert granted.json()["can_manage_worker_money"] is True
    assert set((await session.get(TenantMembership, 10)).permissions) == {
        "catalog.master.edit",
        "worker.money.manage",
        "worker.pay.manage",
    }
    removed = await client.patch(
        path, headers=headers(4), json={"can_manage_worker_pay": False}
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["can_manage_worker_pay"] is False
    assert set((await session.get(TenantMembership, 10)).permissions) == {
        "catalog.master.edit",
        "worker.money.manage",
    }


async def test_financial_delegation_requires_live_owner_and_team_origin(
    money_permission_client,  # noqa: F811
):
    _, client = money_permission_client
    path, payload = "/api/manager/staff/10", {"can_manage_worker_pay": True}
    assert (
        await client.patch(path, headers=headers(4, team=False), json=payload)
    ).status_code == 403
    assert (
        await client.patch(path, headers=headers(), json=payload)
    ).status_code == 403
    support = await client.patch(
        path, headers=headers(4, 2), json={**payload, "primary_role": "manager"}
    )
    assert support.status_code == 200, support.text
    assert support.json()["can_manage_worker_pay"] is True


async def test_non_crm_role_cannot_keep_financial_grants(money_permission_client):  # noqa: F811
    session, client = money_permission_client
    member = await session.get(TenantMembership, 10)
    member.permissions = [
        "catalog.master.edit",
        "worker.money.manage",
        "worker.pay.manage",
    ]
    await session.commit()
    response = await client.patch(
        "/api/manager/staff/10", headers=headers(4), json={"primary_role": "installer"}
    )
    assert response.status_code == 200, response.text
    assert (await session.get(TenantMembership, 10)).permissions == [
        "catalog.master.edit"
    ]
    assert response.json()["can_manage_worker_pay"] is False


def test_pay_capabilities_follow_separate_real_membership_grant():
    assert "worker.pay.read" not in Caps.for_auth(auth())
    pay = Caps.for_auth(replace(auth(), permissions=("worker.pay.manage",)))
    assert {"worker.pay.read", "worker.pay.manage"} <= set(pay)
    assert "worker.money.manage" not in pay
    assert "worker.pay.read" not in Caps.for_auth(
        replace(auth(), permissions=("worker.money.manage",))
    )
    assert "worker.pay.manage" not in Caps.for_auth(
        replace(auth(), role="installer", permissions=("worker.pay.manage",))
    )
    support = Caps.for_auth(
        replace(
            auth(4, 2),
            role="owner",
            access_kind="platform_support",
            is_platform_owner=True,
        )
    )
    assert "worker.pay.read" in support
    assert "worker.pay.manage" not in support
    assert "worker.money.manage" not in support
