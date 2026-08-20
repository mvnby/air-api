from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.security import create_access_token
from models import (
    Customer,
    CustomerEquipment,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
)
from models.common import CustomerType


async def _create_owner(
    db,
    *,
    tenant_id: int,
    username: str,
) -> StaffUser:
    owner = StaffUser(
        display_name=username,
        status="active",
        roles=["owner"],
        primary_role="owner",
        username=username,
    )
    db.add(owner)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    return owner


def _headers(owner: StaffUser) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": owner.username,
            "staff_user_id": owner.id,
            "auth_version": owner.auth_version,
            "auth_source": "warranty-coverage-scope-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_warranty_coverage_read_and_decision_are_tenant_scoped_and_atomic(
    async_client: AsyncClient,
    db,
):
    tenant_b = Tenant(
        id=2,
        slug="warranty-tenant-b",
        display_name="Warranty Tenant B",
        status="active",
        is_system=False,
    )
    db.add(tenant_b)
    await db.flush()
    storefront_b = Storefront(
        id=2,
        tenant_id=int(tenant_b.id),
        slug="main",
        display_name="Warranty Tenant B Main",
        status="active",
        is_default=True,
    )
    db.add(storefront_b)
    await db.flush()

    owner_a = await _create_owner(
        db,
        tenant_id=1,
        username="warranty-owner-a",
    )
    owner_b = await _create_owner(
        db,
        tenant_id=int(tenant_b.id),
        username="warranty-owner-b",
    )
    customer_a = Customer(
        tenant_id=1,
        name="Warranty customer A",
        phone="+375290000081",
        type=CustomerType.individual,
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="Warranty customer B",
        phone="+375290000082",
        type=CustomerType.individual,
    )
    db.add_all([customer_a, customer_b])
    await db.flush()
    equipment_a = CustomerEquipment(
        customer_id=int(customer_a.id),
        display_name="Tenant A equipment",
    )
    equipment_b = CustomerEquipment(
        customer_id=int(customer_b.id),
        display_name="Tenant B equipment",
    )
    db.add_all([equipment_a, equipment_b])
    await db.flush()
    coverage_a = EquipmentWarrantyCoverage(
        equipment_id=int(equipment_a.id),
        coverage_type="supplier",
        terms_snapshot="Tenant A private warranty terms",
        policy_snapshot={"owner": "tenant-a"},
    )
    coverage_b = EquipmentWarrantyCoverage(
        equipment_id=int(equipment_b.id),
        coverage_type="supplier",
        terms_snapshot="Tenant B private warranty terms",
        policy_snapshot={"owner": "tenant-b"},
    )
    db.add_all([coverage_a, coverage_b])
    await db.commit()

    headers_b = _headers(owner_b)
    owned_list = await async_client.get(
        f"/api/manager/equipment/{equipment_b.id}/warranty-coverages",
        headers=headers_b,
    )
    foreign_list = await async_client.get(
        f"/api/manager/equipment/{equipment_a.id}/warranty-coverages",
        headers=headers_b,
    )
    missing_list = await async_client.get(
        "/api/manager/equipment/999999/warranty-coverages",
        headers=headers_b,
    )
    assert owned_list.status_code == 200
    assert [item["id"] for item in owned_list.json()] == [coverage_b.id]
    assert foreign_list.status_code == 404
    assert missing_list.status_code == 404

    foreign_before = {
        "decision_status": coverage_a.decision_status,
        "decision_reason": coverage_a.decision_reason,
        "decided_at": coverage_a.decided_at,
        "decided_by": coverage_a.decided_by,
        "updated_at": coverage_a.updated_at,
    }
    foreign_decision = await async_client.post(
        f"/api/manager/warranty-coverages/{coverage_a.id}/decision",
        headers=headers_b,
        json={"action": "voided", "reason": "Cross-tenant mutation"},
    )
    missing_decision = await async_client.post(
        "/api/manager/warranty-coverages/999999/decision",
        headers=headers_b,
        json={"action": "voided", "reason": "Missing coverage"},
    )
    assert foreign_decision.status_code == 404
    assert missing_decision.status_code == 404

    await db.refresh(coverage_a)
    assert {
        "decision_status": coverage_a.decision_status,
        "decision_reason": coverage_a.decision_reason,
        "decided_at": coverage_a.decided_at,
        "decided_by": coverage_a.decided_by,
        "updated_at": coverage_a.updated_at,
    } == foreign_before
    decisions_before_positive = list(
        (await db.execute(select(EquipmentWarrantyDecision))).scalars()
    )
    assert decisions_before_positive == []

    owned_decision = await async_client.post(
        f"/api/manager/warranty-coverages/{coverage_b.id}/decision",
        headers=headers_b,
        json={"action": "voided", "reason": "Owned warranty decision"},
    )
    assert owned_decision.status_code == 200, owned_decision.text
    assert owned_decision.json()["decision_status"] == "voided"
    assert owned_decision.json()["decision_reason"] == "Owned warranty decision"

    await db.refresh(coverage_b)
    decisions = list(
        (await db.execute(select(EquipmentWarrantyDecision))).scalars()
    )
    assert coverage_b.decision_status == "voided"
    assert coverage_b.decision_reason == "Owned warranty decision"
    assert len(decisions) == 1
    assert decisions[0].coverage_id == coverage_b.id
    assert decisions[0].decided_by == owner_b.username

    # The system tenant remains unable to cross the same tenant boundary.
    system_foreign = await async_client.get(
        f"/api/manager/equipment/{equipment_b.id}/warranty-coverages",
        headers=_headers(owner_a),
    )
    assert system_foreign.status_code == 404
