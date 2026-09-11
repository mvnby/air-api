from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    Brand,
    Customer,
    CustomerEquipment,
    EquipmentMaintenanceReminder,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    Product,
    ProductSeries,
    Supplier,
    WarrantyPolicy,
    WarrantyPolicySeriesLink,
)
from models.tenancy import TenantScope
from services.warranty_coverage_service import WarrantyCoverageService
from services.warranty_service import WarrantyService
from services.warranty_maintenance_service import WarrantyMaintenanceService
from services.equipment_warranty_bridge_service import EquipmentWarrantyBridgeService


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def _create_scoped_equipment(
    session: AsyncSession,
    *,
    equipment_id: int,
) -> CustomerEquipment:
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name=f"Warranty customer {equipment_id}",
        phone=f"+37529{equipment_id:07d}",
    )
    session.add(customer)
    await session.flush()
    equipment = CustomerEquipment(
        id=equipment_id,
        customer_id=int(customer.id),
    )
    session.add(equipment)
    await session.flush()
    return equipment


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
async def test_product_policy_stays_more_specific_and_list_includes_scope_names(warranty_session):
    supplier = Supplier(name="Biocond", code="biocond-warranty")
    brand = Brand(title="MDV", slug="mdv-warranty")
    warranty_session.add_all([supplier, brand])
    await warranty_session.flush()
    series = ProductSeries(brand_id=brand.id, title="Integra Pro", slug="integra-pro-warranty")
    warranty_session.add(series)
    await warranty_session.flush()
    product = Product(
        title="MDV Integra Pro 09",
        slug="mdv-integra-pro-09-warranty",
        price=1000,
        brand_id=brand.id,
        series_id=series.id,
    )
    warranty_session.add(product)
    await warranty_session.flush()
    series_policy = WarrantyPolicy(
        name="Series policy",
        supplier_id=supplier.id,
        series_id=series.id,
        duration_months=36,
    )
    combined_legacy_policy = WarrantyPolicy(
        name="Legacy brand and series policy",
        supplier_id=supplier.id,
        brand_id=brand.id,
        series_id=series.id,
        duration_months=40,
    )
    product_policy = WarrantyPolicy(
        name="Product policy",
        supplier_id=supplier.id,
        product_id=product.id,
        duration_months=48,
    )
    warranty_session.add_all([series_policy, combined_legacy_policy, product_policy])
    await warranty_session.flush()

    resolved = await WarrantyService.resolve_policy(
        warranty_session,
        product=product,
        supplier_id=supplier.id,
        at=datetime(2026, 1, 1),
    )
    items = await WarrantyService.list_policies(warranty_session, include_inactive=True)
    product_item = next(item for item in items if item["id"] == product_policy.id)
    series_item = next(item for item in items if item["id"] == series_policy.id)

    assert resolved is product_policy
    assert product_item["supplier_name"] == "Biocond"
    assert product_item["product_title"] == "MDV Integra Pro 09"
    assert series_item["series_title"] == "Integra Pro"
    assert series_item["series_brand_id"] == brand.id


@pytest.mark.asyncio
async def test_multi_series_policy_resolves_before_brand_fallback_and_defaults_maintenance_interval(warranty_session):
    supplier = Supplier(name="Multi supplier", code="multi-series-supplier")
    brand = Brand(title="Multi brand", slug="multi-series-brand")
    warranty_session.add_all([supplier, brand])
    await warranty_session.flush()
    first = ProductSeries(brand_id=brand.id, title="First", slug="multi-series-first")
    second = ProductSeries(brand_id=brand.id, title="Second", slug="multi-series-second")
    warranty_session.add_all([first, second])
    await warranty_session.flush()
    covered_product = Product(
        title="Covered", slug="multi-series-covered", price=1000, brand_id=brand.id, series_id=second.id
    )
    also_covered_product = Product(
        title="Also covered", slug="multi-series-also-covered", price=1000, brand_id=brand.id, series_id=first.id
    )
    fallback_product = Product(
        title="Fallback", slug="multi-series-fallback", price=1000, brand_id=brand.id
    )
    warranty_session.add_all([covered_product, also_covered_product, fallback_product])
    await warranty_session.flush()

    fallback = await WarrantyService.create_policy(
        warranty_session,
        payload={
            "name": "Supplier and brand fallback",
            "supplier_id": supplier.id,
            "brand_id": brand.id,
            "duration_months": 36,
        },
    )
    selected = await WarrantyService.create_policy(
        warranty_session,
        payload={
            "name": "Selected series",
            "supplier_id": supplier.id,
            "series_ids": [second.id, first.id],
            "duration_months": 48,
            "maintenance_required": True,
        },
    )

    assert selected["brand_id"] == brand.id
    assert selected["series_id"] == second.id
    assert selected["series_ids"] == [second.id, first.id]
    assert selected["series_titles"] == ["Second", "First"]
    assert selected["maintenance_interval_months"] == 12
    assert (await warranty_session.get(WarrantyPolicy, selected["id"])).maintenance_interval_months == 12
    explicit_interval = await WarrantyService.update_policy(
        warranty_session,
        policy_id=selected["id"],
        payload={"maintenance_interval_months": 18},
    )
    preserved_interval = await WarrantyService.update_policy(
        warranty_session,
        policy_id=selected["id"],
        payload={"maintenance_required": True},
    )
    assert explicit_interval and explicit_interval["maintenance_interval_months"] == 18
    assert preserved_interval and preserved_interval["maintenance_interval_months"] == 18
    links = list(
        (await warranty_session.execute(select(WarrantyPolicySeriesLink).where(
            WarrantyPolicySeriesLink.policy_id == selected["id"]
        ).order_by(WarrantyPolicySeriesLink.sort_order))).scalars()
    )
    assert [link.series_id for link in links] == [second.id, first.id]

    resolved_selected = await WarrantyService.resolve_policy(
        warranty_session, product=covered_product, supplier_id=supplier.id
    )
    resolved_second_selected_series = await WarrantyService.resolve_policy(
        warranty_session, product=also_covered_product, supplier_id=supplier.id
    )
    resolved_fallback = await WarrantyService.resolve_policy(
        warranty_session, product=fallback_product, supplier_id=supplier.id
    )
    assert resolved_selected and resolved_selected.id == selected["id"]
    assert resolved_second_selected_series and resolved_second_selected_series.id == selected["id"]
    assert resolved_fallback and resolved_fallback.id == fallback["id"]


@pytest.mark.asyncio
async def test_multi_series_update_retains_omitted_series_and_rejects_invalid_replacement(warranty_session):
    first_brand = Brand(title="First brand", slug="multi-series-update-first-brand")
    second_brand = Brand(title="Second brand", slug="multi-series-update-second-brand")
    warranty_session.add_all([first_brand, second_brand])
    await warranty_session.flush()
    first = ProductSeries(brand_id=first_brand.id, title="First", slug="multi-series-update-first")
    second = ProductSeries(brand_id=first_brand.id, title="Second", slug="multi-series-update-second")
    foreign = ProductSeries(brand_id=second_brand.id, title="Foreign", slug="multi-series-update-foreign")
    warranty_session.add_all([first, second, foreign])
    await warranty_session.flush()
    created = await WarrantyService.create_policy(
        warranty_session,
        payload={"name": "Keep series", "brand_id": first_brand.id, "series_ids": [first.id, second.id]},
    )

    renamed = await WarrantyService.update_policy(
        warranty_session, policy_id=created["id"], payload={"name": "Renamed series policy"}
    )
    assert renamed and renamed["series_ids"] == [first.id, second.id]

    with pytest.raises(ValueError, match="one brand"):
        await WarrantyService.update_policy(
            warranty_session, policy_id=created["id"], payload={"series_ids": [first.id, foreign.id]}
        )
    unchanged = await WarrantyService.list_policies(warranty_session, include_inactive=True)
    item = next(item for item in unchanged if item["id"] == created["id"])
    assert item["name"] == "Renamed series policy"
    assert item["series_ids"] == [first.id, second.id]

    cleared = await WarrantyService.update_policy(
        warranty_session, policy_id=created["id"], payload={"series_ids": []}
    )
    assert cleared and cleared["series_id"] is None and cleared["series_ids"] == []


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
async def test_policy_start_event_and_work_maintenance_terms_are_preserved(warranty_session):
    product = Product(title="Policy product", slug="policy-product-start-event", price=1000)
    equipment = CustomerEquipment(
        customer_id=3,
        installed_at=datetime(2026, 2, 10),
        commissioned_at=datetime(2026, 3, 1),
    )
    warranty_session.add_all([product, equipment])
    await warranty_session.flush()
    supplier_policy = WarrantyPolicy(
        name="Installation start",
        product_id=product.id,
        duration_months=24,
        start_event="installation",
    )
    work_policy = WarrantyPolicy(
        name="MVN work with maintenance",
        coverage_type="mvn_work",
        product_id=product.id,
        duration_months=12,
        start_event="installation",
        maintenance_required=True,
        maintenance_interval_months=6,
        grace_period_days=10,
        allowed_maintenance_provider="mvn",
        terms="Annual MVN service required",
    )
    warranty_session.add_all([supplier_policy, work_policy])
    await warranty_session.flush()

    supplier = await WarrantyService.create_supplier_coverage(
        warranty_session,
        equipment=equipment,
        product=product,
        supplier_id=None,
        sale_at=datetime(2026, 1, 15),
    )
    work = await WarrantyService.create_work_coverage(
        warranty_session,
        equipment=equipment,
        duration_months=18,
        starts_at=equipment.installed_at,
        product=product,
    )

    assert supplier is not None
    assert supplier.starts_at == datetime(2026, 2, 10)
    assert work is not None
    assert work.source == "policy_override"
    assert work.maintenance_required is True
    assert work.maintenance_interval_months == 6
    assert work.grace_period_days == 10
    assert work.allowed_maintenance_provider == "mvn"
    assert work.next_maintenance_due_at == datetime(2026, 8, 10)
    assert work.policy_snapshot["maintenance_required"] is True


@pytest.mark.asyncio
async def test_maintenance_advances_only_for_allowed_provider_and_within_grace(warranty_session):
    due_at = datetime(2026, 6, 1, 9, 0)
    coverage = EquipmentWarrantyCoverage(
        equipment_id=50,
        coverage_type="supplier",
        starts_at=datetime(2025, 12, 1, 9, 0),
        expires_at=datetime(2027, 12, 1, 9, 0),
        maintenance_required=True,
        maintenance_interval_months=6,
        grace_period_days=7,
        allowed_maintenance_provider="authorized",
        next_maintenance_due_at=due_at,
    )
    warranty_session.add(coverage)
    await warranty_session.flush()

    wrong_provider = await WarrantyMaintenanceService.apply_maintenance_event(
        warranty_session,
        equipment_id=50,
        event_type=EquipmentServiceEventType.MAINTENANCE,
        event_date=due_at + timedelta(days=2),
        maintenance_provider="external",
    )
    late = await WarrantyMaintenanceService.apply_maintenance_event(
        warranty_session,
        equipment_id=50,
        event_type=EquipmentServiceEventType.MAINTENANCE,
        event_date=due_at + timedelta(days=8),
        maintenance_provider="authorized",
    )
    accepted = await WarrantyMaintenanceService.apply_maintenance_event(
        warranty_session,
        equipment_id=50,
        event_type=EquipmentServiceEventType.MAINTENANCE,
        event_date=due_at + timedelta(days=5),
        maintenance_provider="authorized",
    )

    assert wrong_provider == {"advanced": 0, "skipped": 1}
    assert late == {"advanced": 0, "skipped": 1}
    assert accepted == {"advanced": 1, "skipped": 0}
    assert coverage.next_maintenance_due_at == datetime(2026, 12, 6, 9, 0)


@pytest.mark.asyncio
async def test_manager_restore_uses_latest_verified_late_maintenance(warranty_session):
    due_at = datetime(2026, 5, 1, 9, 0)
    await _create_scoped_equipment(warranty_session, equipment_id=51)
    coverage = EquipmentWarrantyCoverage(
        equipment_id=51,
        coverage_type="supplier",
        starts_at=datetime(2025, 11, 1, 9, 0),
        expires_at=datetime(2027, 11, 1, 9, 0),
        maintenance_required=True,
        maintenance_interval_months=6,
        allowed_maintenance_provider="mvn",
        next_maintenance_due_at=due_at,
        decision_status="voided",
    )
    event = EquipmentServiceHistory(
        equipment_id=51,
        event_type=EquipmentServiceEventType.MAINTENANCE,
        event_date=due_at + timedelta(days=10),
        maintenance_provider="mvn",
    )
    warranty_session.add_all([coverage, event])
    await warranty_session.flush()

    restored = await WarrantyCoverageService.record_decision(
        warranty_session,
        coverage_id=int(coverage.id),
        action="restored",
        reason="Late service accepted after inspection",
        decided_by="manager@example.test",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert restored is not None
    assert restored["decision_status"] == "restored"
    assert restored["next_maintenance_due_at"] == datetime(2026, 11, 11, 9, 0)


@pytest.mark.asyncio
async def test_overdue_reminder_waits_until_grace_period_ends(warranty_session):
    due_at = datetime(2026, 7, 1, 9, 0)
    coverage = EquipmentWarrantyCoverage(
        equipment_id=52,
        coverage_type="supplier",
        maintenance_required=True,
        maintenance_interval_months=12,
        grace_period_days=7,
        next_maintenance_due_at=due_at,
    )
    warranty_session.add(coverage)
    await warranty_session.commit()

    result = await WarrantyService.generate_maintenance_reminders(
        warranty_session,
        now=due_at + timedelta(days=3),
    )
    reminders = list((await warranty_session.execute(select(EquipmentMaintenanceReminder))).scalars().all())

    assert result == {"created": 2, "skipped": 0, "coverages": 1}
    assert {item.reminder_type for item in reminders} == {"due_30_days", "due_7_days"}


@pytest.mark.asyncio
async def test_manual_warranty_fields_create_and_update_one_coverage(warranty_session):
    equipment = CustomerEquipment(
        customer_id=53,
        warranty_started_at=datetime(2026, 1, 1),
        warranty_expires_at=datetime(2028, 1, 1),
        warranty_terms="Manual supplier warranty",
    )
    warranty_session.add(equipment)
    await warranty_session.flush()

    coverage = await EquipmentWarrantyBridgeService.sync_manual_fields(
        warranty_session,
        equipment=equipment,
        payload={"warranty_started_at": equipment.warranty_started_at, "warranty_expires_at": equipment.warranty_expires_at},
    )
    equipment.warranty_expires_at = datetime(2029, 1, 1)
    updated = await EquipmentWarrantyBridgeService.sync_manual_fields(
        warranty_session,
        equipment=equipment,
        payload={"warranty_expires_at": equipment.warranty_expires_at},
    )

    assert coverage is not None
    assert updated is coverage
    assert coverage.source == "manual"
    assert coverage.expires_at == datetime(2029, 1, 1)
    assert len(coverage.policy_snapshot["manual_corrections"]) == 1


@pytest.mark.asyncio
async def test_policy_coverage_manual_override_preserves_original_policy_snapshot(warranty_session):
    equipment = CustomerEquipment(
        customer_id=54,
        warranty_started_at=datetime(2026, 1, 1),
        warranty_expires_at=datetime(2028, 1, 1),
    )
    warranty_session.add(equipment)
    await warranty_session.flush()
    warranty_session.add(
        EquipmentWarrantyCoverage(
            equipment_id=int(equipment.id),
            coverage_type="supplier",
            source="policy",
            expires_at=equipment.warranty_expires_at,
        )
    )
    await warranty_session.flush()

    coverage = await EquipmentWarrantyBridgeService.apply_update(
        warranty_session,
        equipment=equipment,
        payload={
            "warranty_mode": "manual",
            "warranty_started_at": datetime(2026, 1, 31),
            "warranty_duration_months": 1,
        },
        actor="manager@example.test",
    )

    assert coverage is not None
    assert coverage.source == "policy"
    assert coverage.expires_at == datetime(2026, 2, 28)
    assert coverage.policy_snapshot["automatic_coverage_before_manual"]["expires_at"] == "2028-01-01T00:00:00"


@pytest.mark.asyncio
async def test_manual_mode_reuses_root_legacy_coverage_instead_of_creating_competing_supplier(warranty_session):
    equipment = CustomerEquipment(customer_id=55, warranty_mode="auto")
    warranty_session.add(equipment)
    await warranty_session.flush()
    legacy = EquipmentWarrantyCoverage(
        equipment_id=int(equipment.id),
        coverage_type="legacy",
        source="legacy",
        starts_at=datetime(2025, 1, 1),
        expires_at=datetime(2027, 1, 1),
    )
    warranty_session.add(legacy)
    await warranty_session.flush()

    updated = await EquipmentWarrantyBridgeService.apply_update(
        warranty_session,
        equipment=equipment,
        payload={
            "warranty_mode": "manual",
            "warranty_started_at": datetime(2026, 1, 31),
            "warranty_duration_months": 1,
        },
    )
    coverages = list(
        (await warranty_session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == int(equipment.id)
            )
        )).scalars().all()
    )

    assert updated is legacy
    assert coverages == [legacy]
    assert legacy.expires_at == datetime(2026, 2, 28)


@pytest.mark.asyncio
async def test_overdue_reminders_are_idempotent_and_manual_decision_is_audited(warranty_session):
    due_at = datetime(2026, 6, 1, 9, 0, 0)
    await _create_scoped_equipment(warranty_session, equipment_id=42)
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
        tenant_scope=TEST_TENANT_SCOPE,
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
