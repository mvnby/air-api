from datetime import datetime

import pytest
from sqlmodel import select

from core.config import settings
from models import (
    Customer,
    CustomerBranch,
    CustomerEquipment,
    CustomerType,
    EquipmentComponent,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    Tenant,
)
from models.tenancy import TenantScope
from services.equipment_maintenance_plan_service import EquipmentMaintenancePlanService


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_equipment_warranty_modes_preserve_policy_and_component_audit(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(
        tenant_id=1,
        name="Warranty equipment owner",
        phone="+375291112200",
        type=CustomerType.company,
    )
    db.add(customer)
    await db.flush()
    equipment = CustomerEquipment(
        customer_id=int(customer.id),
        display_name="Policy split",
        warranty_mode="auto",
        warranty_started_at=datetime(2026, 5, 1),
        warranty_expires_at=datetime(2028, 5, 1),
    )
    db.add(equipment)
    await db.flush()
    component = EquipmentComponent(equipment_id=int(equipment.id), component_type="outdoor_unit")
    db.add(component)
    await db.flush()
    coverage = EquipmentWarrantyCoverage(
        equipment_id=int(equipment.id),
        coverage_type="supplier",
        source="policy",
        policy_id=None,
        starts_at=datetime(2026, 5, 1),
        expires_at=datetime(2028, 5, 1),
        maintenance_required=True,
        maintenance_interval_months=1,
        allowed_maintenance_provider="mvn",
        next_maintenance_due_at=datetime(2026, 6, 1),
        terms_snapshot="Original policy terms",
        policy_snapshot={"policy_name": "Original policy"},
    )
    component_coverage = EquipmentWarrantyCoverage(
        equipment_id=int(equipment.id),
        component_id=int(component.id),
        coverage_type="supplier",
        source="policy",
        starts_at=datetime(2026, 5, 1),
        expires_at=datetime(2027, 5, 1),
        maintenance_required=True,
        maintenance_interval_months=6,
        next_maintenance_due_at=datetime(2026, 11, 1),
    )
    db.add_all([coverage, component_coverage])
    await db.commit()

    unchanged = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}",
        headers=headers,
        json={
            "notes": "Only registry notes changed",
            "warranty_started_at": "2026-05-01T00:00:00",
            "warranty_expires_at": "2028-05-01T00:00:00",
            "warranty_terms": "Original policy terms",
        },
    )
    assert unchanged.status_code == 200, unchanged.text
    await db.refresh(coverage)
    assert coverage.starts_at == datetime(2026, 5, 1)
    assert coverage.expires_at == datetime(2028, 5, 1)
    assert "manual_corrections" not in coverage.policy_snapshot

    manual = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}",
        headers=headers,
        json={
            "warranty_mode": "manual",
            "warranty_started_at": "2026-01-31T00:00:00",
            "warranty_duration_months": 1,
            "warranty_terms": "Corrected after document review",
        },
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["warranty_mode"] == "manual"
    assert manual.json()["warranty_expires_at"].startswith("2026-02-28")
    await db.refresh(coverage)
    assert coverage.source == "policy"
    assert coverage.maintenance_required is True
    assert coverage.allowed_maintenance_provider == "mvn"
    assert coverage.next_maintenance_due_at == datetime(2026, 2, 28)
    assert coverage.policy_snapshot["automatic_coverage_before_manual"]["expires_at"] == "2028-05-01T00:00:00"
    manual_detail = await async_client.get(f"/api/manager/equipment/{equipment.id}", headers=headers)
    assert manual_detail.status_code == 200
    assert manual_detail.json()["warranty_expires_at"].startswith("2026-02-28")
    manual_list = await async_client.get(
        f"/api/manager/equipment?customer_id={customer.id}",
        headers=headers,
    )
    assert manual_list.status_code == 200
    manual_list_item = next(item for item in manual_list.json()["items"] if item["id"] == equipment.id)
    assert manual_list_item["warranty_expires_at"].startswith("2026-02-28")

    automatic = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}",
        headers=headers,
        json={"warranty_mode": "auto"},
    )
    assert automatic.status_code == 200, automatic.text
    assert automatic.json()["warranty_expires_at"].startswith("2028-05-01")
    await db.refresh(coverage)
    assert coverage.next_maintenance_due_at == datetime(2026, 6, 1)

    without_warranty = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}",
        headers=headers,
        json={"warranty_mode": "none"},
    )
    assert without_warranty.status_code == 200, without_warranty.text
    assert without_warranty.json()["warranty_status"] == "none"
    await db.refresh(coverage)
    await db.refresh(component_coverage)
    assert coverage.decision_status == "voided"
    assert component_coverage.decision_status == "voided"

    blocked_restore = await async_client.post(
        f"/api/manager/warranty-coverages/{coverage.id}/decision",
        headers=headers,
        json={"action": "restored", "reason": "Must switch mode first"},
    )
    assert blocked_restore.status_code == 400
    assert "Switch equipment warranty mode" in blocked_restore.text

    detail = await async_client.get(f"/api/manager/equipment/{equipment.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["customer_phone"] == customer.phone
    assert detail.json()["warranty_status"] == "none"
    assert "needs_decision" not in detail.json()["attention_reasons"]
    decisions = list(
        (await db.execute(select(EquipmentWarrantyDecision).where(
            EquipmentWarrantyDecision.coverage_id.in_([coverage.id, component_coverage.id])
        ))).scalars().all()
    )
    assert {item.action for item in decisions} >= {"voided"}

    fresh_manual = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer.id,
            "display_name": "Fresh manual warranty",
            "warranty_mode": "manual",
            "warranty_started_at": "2026-01-31T00:00:00",
            "warranty_duration_months": 1,
        },
    )
    assert fresh_manual.status_code == 201, fresh_manual.text
    fresh_id = fresh_manual.json()["id"]
    fresh_auto = await async_client.patch(
        f"/api/manager/equipment/{fresh_id}",
        headers=headers,
        json={"warranty_mode": "auto"},
    )
    assert fresh_auto.status_code == 200, fresh_auto.text
    assert fresh_auto.json()["warranty_status"] == "unknown"
    assert fresh_auto.json()["warranty_expires_at"] is None
    fresh_manual_again = await async_client.patch(
        f"/api/manager/equipment/{fresh_id}",
        headers=headers,
        json={
            "warranty_mode": "manual",
            "warranty_started_at": "2026-02-28T00:00:00",
            "warranty_duration_months": 12,
        },
    )
    assert fresh_manual_again.status_code == 200, fresh_manual_again.text
    assert fresh_manual_again.json()["warranty_status"] in {"active", "expired"}
    fresh_coverage = (
        await db.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == fresh_id,
                EquipmentWarrantyCoverage.component_id.is_(None),
            )
        )
    ).scalars().one()
    assert fresh_coverage.decision_status == "restored"
    assert fresh_coverage.expires_at == datetime(2027, 2, 28)


@pytest.mark.asyncio
async def test_independent_maintenance_plan_uses_real_maintenance_and_is_tenant_scoped(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(
        tenant_id=1,
        name="Maintenance owner",
        phone="+375291112201",
        type=CustomerType.company,
    )
    db.add(customer)
    await db.flush()
    branch = CustomerBranch(
        customer_id=int(customer.id),
        name="Server room",
        delivery_address="Minsk, Test 1",
        contact_name="Service contact",
        contact_phone="+375291119999",
    )
    db.add(branch)
    await db.commit()

    missing_anchor = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer.id,
            "display_name": "Invalid maintenance plan",
            "maintenance_enabled": True,
        },
    )
    assert missing_anchor.status_code == 400
    assert "requires an anchor" in missing_anchor.text

    created = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer.id,
            "customer_branch_id": branch.id,
            "display_name": "Monthly split",
            "installed_at": "2024-01-31T10:00:00",
            "maintenance_enabled": True,
            "maintenance_interval_months": 1,
        },
    )
    assert created.status_code == 201, created.text
    equipment_id = created.json()["id"]
    assert created.json()["warranty_status"] == "unknown"
    assert created.json()["next_maintenance_due_at"].startswith("2024-02-29T10:00:00")

    maintenance = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={
            "event_type": "maintenance",
            "event_date": "2024-02-29T09:00:00",
            "maintenance_provider": "external",
        },
    )
    assert maintenance.status_code == 201, maintenance.text
    repair = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={"event_type": "repair", "event_date": "2024-03-30T09:00:00"},
    )
    assert repair.status_code == 201, repair.text

    detail = await async_client.get(f"/api/manager/equipment/{equipment_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["last_service_at"].startswith("2024-02-29T09:00:00")
    assert detail.json()["next_maintenance_due_at"].startswith("2024-03-29T09:00:00")
    assert detail.json()["service_contact_phone"] == branch.contact_phone

    foreign_tenant = Tenant(
        slug="maintenance-foreign",
        display_name="Maintenance foreign",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(foreign_tenant)
    await db.flush()
    foreign_customer = Customer(
        tenant_id=int(foreign_tenant.id),
        name="Foreign owner",
        phone="+375291112202",
        type=CustomerType.company,
    )
    db.add(foreign_customer)
    await db.flush()
    foreign_equipment = CustomerEquipment(
        customer_id=int(foreign_customer.id),
        display_name="Foreign split",
        installed_at=datetime(2024, 3, 5),
        maintenance_enabled=True,
        maintenance_interval_months=1,
    )
    db.add(foreign_equipment)
    await db.commit()

    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=False)
    scheduled = await EquipmentMaintenancePlanService.calendar_events(
        db,
        start_date=datetime(2024, 3, 1),
        end_date=datetime(2024, 3, 31, 23, 59),
        tenant_scope=scope,
        now=datetime(2024, 3, 15, 12, 0),
    )
    assert [item["equipment_id"] for item in scheduled] == [equipment_id]
    assert scheduled[0]["order_id"] is None
    assert scheduled[0]["date"] == datetime(2024, 3, 29, 9, 0)
    assert scheduled[0]["start"] == datetime(2024, 3, 29, 9, 0)
    assert scheduled[0]["title"] == "Предложить ТО: Maintenance owner · Monthly split"

    overdue = await EquipmentMaintenancePlanService.calendar_events(
        db,
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 4, 30, 23, 59),
        tenant_scope=scope,
        now=datetime(2024, 4, 5, 12, 0),
    )
    assert overdue[0]["status"] == "overdue"
    assert overdue[0]["date"] == datetime(2024, 3, 29, 9, 0)
    assert overdue[0]["start"] == datetime(2024, 4, 5)
    assert overdue[0]["title"] == "Просрочено ТО: Maintenance owner · Monthly split"

    historical = await EquipmentMaintenancePlanService.calendar_events(
        db,
        start_date=datetime(2024, 3, 1),
        end_date=datetime(2024, 3, 31, 23, 59),
        tenant_scope=scope,
        now=datetime(2024, 4, 5, 12, 0),
    )
    assert historical == []

    disabled = await async_client.patch(
        f"/api/manager/equipment/{equipment_id}",
        headers=headers,
        json={"maintenance_enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["next_maintenance_due_at"] is None
    cleared_anchor = await async_client.patch(
        f"/api/manager/equipment/{equipment_id}",
        headers=headers,
        json={"installed_at": None, "maintenance_enabled": True},
    )
    assert cleared_anchor.status_code == 400
    assert "requires an anchor" in cleared_anchor.text
    archived = await async_client.patch(
        f"/api/manager/equipment/{equipment_id}",
        headers=headers,
        json={"maintenance_enabled": True, "is_archived": True},
    )
    assert archived.status_code == 200
    archived_events = await EquipmentMaintenancePlanService.calendar_events(
        db,
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 4, 30, 23, 59),
        tenant_scope=scope,
        now=datetime(2024, 4, 5, 12, 0),
    )
    assert archived_events == []
