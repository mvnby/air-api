from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    CustomerEquipment,
    EquipmentMaintenanceReminder,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    Product,
    WarrantyPolicy,
)
from services.warranty_service import WarrantyService


@pytest.fixture
async def warranty_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warranties.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_product_policy_wins_and_coverage_keeps_policy_snapshot(warranty_session):
    commissioned_at = datetime(2026, 1, 31, 12, 0, 0)
    product = Product(
        title="Test split",
        slug="test-split-policy-priority",
        price=1000,
        brand_id=10,
        series_id=20,
        specs={"warranty_months": 24},
    )
    equipment = CustomerEquipment(customer_id=1, commissioned_at=commissioned_at)
    warranty_session.add_all([product, equipment])
    await warranty_session.flush()
    policies = [
        WarrantyPolicy(name="Supplier", supplier_id=30, duration_months=12),
        WarrantyPolicy(name="Brand", brand_id=10, duration_months=24),
        WarrantyPolicy(name="Series", series_id=20, duration_months=36),
        WarrantyPolicy(
            name="Product",
            product_id=int(product.id),
            duration_months=48,
            maintenance_required=True,
            maintenance_interval_months=6,
            grace_period_days=14,
            allowed_maintenance_provider="authorized",
            terms="Original terms",
        ),
    ]
    warranty_session.add_all(policies)
    await warranty_session.flush()

    resolved = await WarrantyService.resolve_policy(
        warranty_session,
        product=product,
        supplier_id=30,
        at=commissioned_at,
    )
    coverage = await WarrantyService.create_supplier_coverage(
        warranty_session,
        equipment=equipment,
        product=product,
        supplier_id=30,
    )

    assert resolved is policies[-1]
    assert coverage is not None
    assert coverage.policy_id == policies[-1].id
    assert coverage.source == "policy"
    assert coverage.starts_at == commissioned_at
    assert coverage.expires_at == datetime(2030, 1, 31, 12, 0, 0)
    assert coverage.next_maintenance_due_at == datetime(2026, 7, 31, 12, 0, 0)
    assert coverage.policy_snapshot["duration_months"] == 48
    assert coverage.policy_snapshot["terms"] == "Original terms"

    policies[-1].duration_months = 6
    policies[-1].terms = "Changed later"
    await warranty_session.commit()
    await warranty_session.refresh(coverage)
    assert coverage.expires_at == datetime(2030, 1, 31, 12, 0, 0)
    assert coverage.policy_snapshot["duration_months"] == 48
    assert coverage.terms_snapshot == "Original terms"


@pytest.mark.asyncio
async def test_supplier_coverage_has_no_implicit_24_month_fallback(warranty_session):
    product = Product(
        title="No warranty data",
        slug="no-warranty-data",
        price=1000,
        specs={},
    )
    equipment = CustomerEquipment(customer_id=2, commissioned_at=datetime(2026, 2, 1))
    warranty_session.add_all([product, equipment])
    await warranty_session.flush()

    coverage = await WarrantyService.create_supplier_coverage(
        warranty_session,
        equipment=equipment,
        product=product,
        supplier_id=None,
    )

    assert coverage is None
    assert list((await warranty_session.execute(select(EquipmentWarrantyCoverage))).scalars()) == []


@pytest.mark.asyncio
async def test_overdue_reminders_are_idempotent_and_manual_decision_is_audited(warranty_session):
    due_at = datetime(2026, 6, 1, 9, 0, 0)
    coverage = EquipmentWarrantyCoverage(
        equipment_id=42,
        coverage_type="supplier",
        starts_at=datetime(2025, 12, 1, 9, 0, 0),
        expires_at=datetime(2027, 12, 1, 9, 0, 0),
        maintenance_required=True,
        maintenance_interval_months=6,
        grace_period_days=7,
        next_maintenance_due_at=due_at,
    )
    warranty_session.add(coverage)
    await warranty_session.commit()

    now = due_at + timedelta(days=8)
    assert WarrantyService.coverage_status(coverage, now=now) == {
        "time_status": "active",
        "maintenance_status": "overdue",
        "requires_manager_decision": True,
    }
    first = await WarrantyService.generate_maintenance_reminders(warranty_session, now=now)
    second = await WarrantyService.generate_maintenance_reminders(warranty_session, now=now)
    reminders = list(
        (await warranty_session.execute(select(EquipmentMaintenanceReminder))).scalars().all()
    )
    assert first == {"created": 3, "skipped": 0, "coverages": 1}
    assert second == {"created": 0, "skipped": 3, "coverages": 1}
    assert {item.reminder_type for item in reminders} == {"due_30_days", "due_7_days", "overdue"}

    result = await WarrantyService.record_decision(
        warranty_session,
        coverage_id=int(coverage.id),
        action="voided",
        reason="  Maintenance was completed outside the allowed provider.  ",
        decided_by="manager@example.test",
    )
    decisions = list(
        (await warranty_session.execute(select(EquipmentWarrantyDecision))).scalars().all()
    )
    assert result is not None
    assert result["decision_status"] == "voided"
    assert result["decision_reason"] == "Maintenance was completed outside the allowed provider."
    assert result["requires_manager_decision"] is False
    assert len(decisions) == 1
    assert decisions[0].action == "voided"
    assert decisions[0].decided_by == "manager@example.test"

