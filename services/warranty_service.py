"""Warranty policy resolution and immutable equipment coverage snapshots."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Brand,
    CustomerEquipment,
    EquipmentMaintenanceReminder,
    EquipmentServiceEventType,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    Product,
    ProductSeries,
    Supplier,
    WarrantyPolicy,
)


class WarrantyService:
    COVERAGE_TYPES = {"supplier", "mvn_work", "legacy"}
    DECISIONS = {"voided", "restored"}
    REMINDER_THRESHOLDS = {
        "due_30_days": timedelta(days=30),
        "due_7_days": timedelta(days=7),
        "overdue": timedelta(0),
    }

    @staticmethod
    def policy_to_item(policy: WarrantyPolicy) -> dict[str, Any]:
        return {
            "id": int(policy.id or 0),
            "name": policy.name,
            "coverage_type": policy.coverage_type,
            "supplier_id": policy.supplier_id,
            "brand_id": policy.brand_id,
            "series_id": policy.series_id,
            "product_id": policy.product_id,
            "duration_months": policy.duration_months,
            "start_event": policy.start_event,
            "maintenance_required": bool(policy.maintenance_required),
            "maintenance_interval_months": policy.maintenance_interval_months,
            "grace_period_days": int(policy.grace_period_days or 0),
            "allowed_maintenance_provider": policy.allowed_maintenance_provider,
            "terms": policy.terms,
            "effective_from": policy.effective_from,
            "effective_until": policy.effective_until,
            "is_active": bool(policy.is_active),
            "created_at": policy.created_at,
            "updated_at": policy.updated_at,
        }

    @classmethod
    def _validated_policy_values(cls, payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
        values = dict(payload)
        if "name" in values:
            values["name"] = " ".join(str(values.get("name") or "").split())
            if not values["name"]:
                raise ValueError("Warranty policy name is required")
        elif not partial:
            raise ValueError("Warranty policy name is required")
        if "coverage_type" in values:
            coverage_type = str(values.get("coverage_type") or "").strip()
            if coverage_type not in {"supplier", "mvn_work"}:
                raise ValueError("Unsupported warranty coverage type")
            values["coverage_type"] = coverage_type
        if "duration_months" in values and values["duration_months"] is not None:
            values["duration_months"] = int(values["duration_months"])
            if not 0 < values["duration_months"] <= 240:
                raise ValueError("Warranty duration must be between 1 and 240 months")
        if "maintenance_interval_months" in values and values["maintenance_interval_months"] is not None:
            values["maintenance_interval_months"] = int(values["maintenance_interval_months"])
            if not 0 < values["maintenance_interval_months"] <= 60:
                raise ValueError("Maintenance interval must be between 1 and 60 months")
        if values.get("maintenance_required") is True and not values.get("maintenance_interval_months") and not partial:
            raise ValueError("Maintenance interval is required when maintenance is mandatory")
        if "grace_period_days" in values:
            values["grace_period_days"] = int(values.get("grace_period_days") or 0)
            if not 0 <= values["grace_period_days"] <= 365:
                raise ValueError("Warranty grace period must be between 0 and 365 days")
        if "start_event" in values and values["start_event"] not in {"sale", "installation", "commissioning", "manual"}:
            raise ValueError("Unsupported warranty start event")
        if "allowed_maintenance_provider" in values and values["allowed_maintenance_provider"] not in {
            "any",
            "mvn",
            "authorized",
        }:
            raise ValueError("Unsupported maintenance provider rule")
        return values

    @classmethod
    async def list_policies(
        cls,
        session: AsyncSession,
        *,
        supplier_id: int | None = None,
        brand_id: int | None = None,
        series_id: int | None = None,
        product_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        filters = []
        if supplier_id is not None:
            filters.append(WarrantyPolicy.supplier_id == supplier_id)
        if brand_id is not None:
            filters.append(WarrantyPolicy.brand_id == brand_id)
        if series_id is not None:
            filters.append(WarrantyPolicy.series_id == series_id)
        if product_id is not None:
            filters.append(WarrantyPolicy.product_id == product_id)
        if not include_inactive:
            filters.append(WarrantyPolicy.is_active == True)
        result = await session.execute(
            select(WarrantyPolicy)
            .where(*filters)
            .order_by(WarrantyPolicy.is_active.desc(), WarrantyPolicy.name, WarrantyPolicy.id)
        )
        return [cls.policy_to_item(item) for item in result.scalars().all()]

    @classmethod
    async def create_policy(cls, session: AsyncSession, *, payload: dict[str, Any]) -> dict[str, Any]:
        values = cls._validated_policy_values(payload, partial=False)
        if not any(values.get(key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(session, values)
        policy = WarrantyPolicy(**values)
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        return cls.policy_to_item(policy)

    @classmethod
    async def update_policy(
        cls,
        session: AsyncSession,
        *,
        policy_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        policy = await session.get(WarrantyPolicy, policy_id)
        if not policy:
            return None
        values = cls._validated_policy_values(payload, partial=True)
        for field, value in values.items():
            setattr(policy, field, value)
        if policy.maintenance_required and not policy.maintenance_interval_months:
            raise ValueError("Maintenance interval is required when maintenance is mandatory")
        if not any(getattr(policy, key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(
            session,
            {
                "supplier_id": policy.supplier_id,
                "brand_id": policy.brand_id,
                "series_id": policy.series_id,
                "product_id": policy.product_id,
            },
        )
        policy.updated_at = datetime.now()
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        return cls.policy_to_item(policy)

    @staticmethod
    async def _validate_policy_scope(session: AsyncSession, values: dict[str, Any]) -> None:
        supplier_id = values.get("supplier_id")
        brand_id = values.get("brand_id")
        series_id = values.get("series_id")
        product_id = values.get("product_id")
        if supplier_id is not None and not await session.get(Supplier, int(supplier_id)):
            raise ValueError("Warranty policy supplier not found")
        brand = await session.get(Brand, int(brand_id)) if brand_id is not None else None
        if brand_id is not None and not brand:
            raise ValueError("Warranty policy brand not found")
        series = await session.get(ProductSeries, int(series_id)) if series_id is not None else None
        if series_id is not None and not series:
            raise ValueError("Warranty policy series not found")
        product = await session.get(Product, int(product_id)) if product_id is not None else None
        if product_id is not None and not product:
            raise ValueError("Warranty policy product not found")
        if series and brand_id is not None and int(series.brand_id) != int(brand_id):
            raise ValueError("Warranty policy series does not belong to the selected brand")
        if product and brand_id is not None and int(product.brand_id or 0) != int(brand_id):
            raise ValueError("Warranty policy product does not belong to the selected brand")
        if product and series_id is not None and int(product.series_id or 0) != int(series_id):
            raise ValueError("Warranty policy product does not belong to the selected series")

    @staticmethod
    async def _existing_system_coverage(
        session: AsyncSession,
        *,
        equipment_id: int,
        coverage_type: str,
    ) -> EquipmentWarrantyCoverage | None:
        result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == equipment_id,
                EquipmentWarrantyCoverage.component_id.is_(None),
                EquipmentWarrantyCoverage.coverage_type == coverage_type,
            )
        )
        return result.scalars().first()

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        from services.equipment_service import EquipmentService

        return EquipmentService._add_months(value, months)

    @staticmethod
    def _warranty_months_from_product(product: Product | None) -> int | None:
        specs = getattr(product, "specs", None) if product else None
        if not isinstance(specs, dict):
            return None
        raw: Any = specs.get("warranty_months")
        if isinstance(raw, dict):
            raw = raw.get("value") or raw.get("normalized") or raw.get("raw")
        if isinstance(raw, (int, float)):
            value = int(raw)
            return value if value > 0 else None
        match = re.search(r"\d+", str(raw or ""))
        if not match:
            return None
        value = int(match.group())
        return value if 0 < value <= 240 else None

    @staticmethod
    def _policy_matches(
        policy: WarrantyPolicy,
        *,
        product: Product | None,
        supplier_id: int | None,
    ) -> bool:
        if policy.supplier_id is not None and int(policy.supplier_id) != int(supplier_id or 0):
            return False
        if policy.product_id is not None and (not product or int(policy.product_id) != int(product.id or 0)):
            return False
        if policy.series_id is not None and (not product or int(policy.series_id) != int(product.series_id or 0)):
            return False
        if policy.brand_id is not None and (not product or int(policy.brand_id) != int(product.brand_id or 0)):
            return False
        return True

    @staticmethod
    def _policy_score(policy: WarrantyPolicy) -> int:
        return (
            (1000 if policy.product_id is not None else 0)
            + (700 if policy.series_id is not None else 0)
            + (400 if policy.brand_id is not None else 0)
            + (100 if policy.supplier_id is not None else 0)
        )

    @classmethod
    async def resolve_policy(
        cls,
        session: AsyncSession,
        *,
        product: Product | None,
        supplier_id: int | None,
        coverage_type: str = "supplier",
        at: datetime | None = None,
    ) -> WarrantyPolicy | None:
        moment = cls._naive(at) or datetime.now()
        result = await session.execute(
            select(WarrantyPolicy).where(
                WarrantyPolicy.is_active == True,
                WarrantyPolicy.coverage_type == coverage_type,
            )
        )
        candidates = []
        for policy in result.scalars().all():
            if policy.effective_from and cls._naive(policy.effective_from) > moment:
                continue
            if policy.effective_until and cls._naive(policy.effective_until) < moment:
                continue
            if cls._policy_matches(policy, product=product, supplier_id=supplier_id):
                candidates.append(policy)
        candidates.sort(key=lambda item: (cls._policy_score(item), item.created_at, item.id or 0), reverse=True)
        return candidates[0] if candidates else None

    @staticmethod
    def _start_for_event(
        *,
        event: str,
        equipment: CustomerEquipment,
        explicit: datetime | None,
    ) -> datetime | None:
        if explicit:
            return WarrantyService._naive(explicit)
        if event == "installation":
            return WarrantyService._naive(equipment.installed_at)
        if event == "sale":
            return WarrantyService._naive(equipment.commissioned_at or equipment.installed_at)
        if event == "manual":
            return None
        return WarrantyService._naive(equipment.commissioned_at or equipment.installed_at)

    @classmethod
    async def create_supplier_coverage(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        product: Product | None,
        supplier_id: int | None,
        explicit_start: datetime | None = None,
    ) -> EquipmentWarrantyCoverage | None:
        existing = await cls._existing_system_coverage(
            session,
            equipment_id=int(equipment.id or 0),
            coverage_type="supplier",
        )
        if existing:
            return existing
        policy = await cls.resolve_policy(
            session,
            product=product,
            supplier_id=supplier_id,
            coverage_type="supplier",
            at=explicit_start,
        )
        if policy:
            duration_months = policy.duration_months
            start_event = policy.start_event
            maintenance_required = bool(policy.maintenance_required)
            interval = policy.maintenance_interval_months
            grace = int(policy.grace_period_days or 0)
            provider = policy.allowed_maintenance_provider or "any"
            terms = policy.terms
            source = "policy"
            snapshot = {
                "policy_id": policy.id,
                "policy_name": policy.name,
                "supplier_id": policy.supplier_id,
                "brand_id": policy.brand_id,
                "series_id": policy.series_id,
                "product_id": policy.product_id,
                "duration_months": policy.duration_months,
                "start_event": policy.start_event,
                "maintenance_required": policy.maintenance_required,
                "maintenance_interval_months": policy.maintenance_interval_months,
                "grace_period_days": policy.grace_period_days,
                "allowed_maintenance_provider": policy.allowed_maintenance_provider,
                "terms": policy.terms,
            }
        else:
            duration_months = cls._warranty_months_from_product(product)
            if duration_months is None:
                return None
            start_event = "commissioning"
            maintenance_required = False
            interval = None
            grace = 0
            provider = "any"
            terms = None
            source = "product_spec"
            snapshot = {
                "duration_months": duration_months,
                "source_spec": "warranty_months",
                "product_id": int(product.id or 0) if product else None,
            }

        starts_at = cls._start_for_event(event=start_event, equipment=equipment, explicit=explicit_start)
        expires_at = cls._add_months(starts_at, duration_months) if starts_at and duration_months else None
        next_due = cls._add_months(starts_at, interval) if starts_at and maintenance_required and interval else None
        coverage = EquipmentWarrantyCoverage(
            equipment_id=int(equipment.id or 0),
            policy_id=policy.id if policy else None,
            coverage_type="supplier",
            source=source,
            starts_at=starts_at,
            expires_at=expires_at,
            maintenance_required=maintenance_required,
            maintenance_interval_months=interval,
            grace_period_days=grace,
            allowed_maintenance_provider=provider,
            next_maintenance_due_at=next_due,
            terms_snapshot=terms,
            policy_snapshot=snapshot,
        )
        session.add(coverage)
        await session.flush()
        return coverage

    @classmethod
    async def create_work_coverage(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        duration_months: int | None,
        starts_at: datetime | None,
        terms: str | None = None,
        product: Product | None = None,
        supplier_id: int | None = None,
    ) -> EquipmentWarrantyCoverage | None:
        existing = await cls._existing_system_coverage(
            session,
            equipment_id=int(equipment.id or 0),
            coverage_type="mvn_work",
        )
        if existing:
            return existing
        policy = None
        if duration_months is None:
            policy = await cls.resolve_policy(
                session,
                product=product,
                supplier_id=supplier_id,
                coverage_type="mvn_work",
                at=starts_at,
            )
            duration_months = policy.duration_months if policy else None
            terms = policy.terms if policy else terms
        if duration_months is None or int(duration_months) <= 0:
            return None
        start = cls._naive(starts_at) or cls._naive(equipment.installed_at or equipment.commissioned_at)
        coverage = EquipmentWarrantyCoverage(
            equipment_id=int(equipment.id or 0),
            policy_id=policy.id if policy else None,
            coverage_type="mvn_work",
            source="policy" if policy else "manual",
            starts_at=start,
            expires_at=cls._add_months(start, int(duration_months)) if start else None,
            maintenance_required=False,
            terms_snapshot=terms,
            policy_snapshot=(
                {
                    "policy_id": policy.id,
                    "policy_name": policy.name,
                    "supplier_id": policy.supplier_id,
                    "brand_id": policy.brand_id,
                    "series_id": policy.series_id,
                    "product_id": policy.product_id,
                    "duration_months": int(duration_months),
                    "start_event": policy.start_event,
                    "terms": policy.terms,
                }
                if policy
                else {"duration_months": int(duration_months), "start_event": "installation"}
            ),
        )
        session.add(coverage)
        await session.flush()
        return coverage

    @classmethod
    def coverage_status(cls, coverage: EquipmentWarrantyCoverage, *, now: datetime | None = None) -> dict[str, Any]:
        moment = cls._naive(now) or datetime.now()
        starts_at = cls._naive(coverage.starts_at)
        expires_at = cls._naive(coverage.expires_at)
        if coverage.decision_status == "voided":
            time_status = "voided"
        elif starts_at and starts_at > moment:
            time_status = "scheduled"
        elif expires_at is None:
            time_status = "unknown"
        else:
            time_status = "active" if expires_at >= moment else "expired"

        if not coverage.maintenance_required:
            maintenance_status = "not_required"
        elif coverage.next_maintenance_due_at is None:
            maintenance_status = "unknown"
        else:
            due_at = cls._naive(coverage.next_maintenance_due_at)
            grace_until = due_at + timedelta(days=int(coverage.grace_period_days or 0))
            if moment > grace_until:
                maintenance_status = "overdue"
            elif moment >= due_at - timedelta(days=30):
                maintenance_status = "due_soon"
            else:
                maintenance_status = "current"
        return {
            "time_status": time_status,
            "maintenance_status": maintenance_status,
            "requires_manager_decision": maintenance_status == "overdue" and coverage.decision_status == "none",
        }

    @classmethod
    def to_item(cls, coverage: EquipmentWarrantyCoverage) -> dict[str, Any]:
        return {
            "id": int(coverage.id or 0),
            "equipment_id": int(coverage.equipment_id),
            "component_id": coverage.component_id,
            "policy_id": coverage.policy_id,
            "coverage_type": coverage.coverage_type,
            "source": coverage.source,
            "starts_at": coverage.starts_at,
            "expires_at": coverage.expires_at,
            "maintenance_required": bool(coverage.maintenance_required),
            "maintenance_interval_months": coverage.maintenance_interval_months,
            "grace_period_days": int(coverage.grace_period_days or 0),
            "allowed_maintenance_provider": coverage.allowed_maintenance_provider,
            "next_maintenance_due_at": coverage.next_maintenance_due_at,
            "terms_snapshot": coverage.terms_snapshot,
            "policy_snapshot": coverage.policy_snapshot,
            "decision_status": coverage.decision_status,
            "decision_reason": coverage.decision_reason,
            "decided_at": coverage.decided_at,
            "decided_by": coverage.decided_by,
            **cls.coverage_status(coverage),
            "created_at": coverage.created_at,
            "updated_at": coverage.updated_at,
        }

    @classmethod
    async def list_coverages(cls, session: AsyncSession, *, equipment_id: int) -> list[dict[str, Any]]:
        result = await session.execute(
            select(EquipmentWarrantyCoverage)
            .where(EquipmentWarrantyCoverage.equipment_id == equipment_id)
            .order_by(EquipmentWarrantyCoverage.coverage_type, EquipmentWarrantyCoverage.id)
        )
        return [cls.to_item(item) for item in result.scalars().all()]

    @classmethod
    async def generate_maintenance_reminders(
        cls,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        moment = cls._naive(now) or datetime.now()
        coverage_result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.maintenance_required == True,
                EquipmentWarrantyCoverage.next_maintenance_due_at.is_not(None),
                EquipmentWarrantyCoverage.decision_status != "voided",
            )
        )
        coverages = list(coverage_result.scalars().all())
        created = 0
        skipped = 0
        for coverage in coverages:
            due_at = cls._naive(coverage.next_maintenance_due_at)
            if due_at is None:
                continue
            for reminder_type, threshold in cls.REMINDER_THRESHOLDS.items():
                if moment < due_at - threshold:
                    continue
                existing = await session.execute(
                    select(EquipmentMaintenanceReminder.id).where(
                        EquipmentMaintenanceReminder.coverage_id == int(coverage.id or 0),
                        EquipmentMaintenanceReminder.reminder_type == reminder_type,
                        EquipmentMaintenanceReminder.due_at == due_at,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    skipped += 1
                    continue
                reminder = EquipmentMaintenanceReminder(
                    equipment_id=int(coverage.equipment_id),
                    coverage_id=int(coverage.id or 0),
                    reminder_type=reminder_type,
                    due_at=due_at,
                )
                try:
                    async with session.begin_nested():
                        session.add(reminder)
                        await session.flush()
                    created += 1
                except IntegrityError:
                    skipped += 1
        await session.commit()
        return {"created": created, "skipped": skipped, "coverages": len(coverages)}

    @staticmethod
    async def _resolve_open_maintenance_reminders(
        session: AsyncSession,
        *,
        equipment_id: int,
        resolved_at: datetime,
    ) -> None:
        result = await session.execute(
            select(EquipmentMaintenanceReminder).where(
                EquipmentMaintenanceReminder.equipment_id == equipment_id,
                EquipmentMaintenanceReminder.status == "open",
            )
        )
        for reminder in result.scalars().all():
            reminder.status = "resolved"
            reminder.resolved_at = resolved_at
            session.add(reminder)

    @classmethod
    async def record_decision(
        cls,
        session: AsyncSession,
        *,
        coverage_id: int,
        action: str,
        reason: str,
        decided_by: str,
    ) -> dict[str, Any] | None:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in cls.DECISIONS:
            raise ValueError("Warranty decision must be voided or restored")
        cleaned_reason = " ".join(str(reason or "").split())
        if not cleaned_reason:
            raise ValueError("Warranty decision reason is required")
        coverage = await session.get(EquipmentWarrantyCoverage, coverage_id)
        if not coverage:
            return None
        coverage.decision_status = normalized_action
        coverage.decision_reason = cleaned_reason
        coverage.decided_at = datetime.now()
        coverage.decided_by = decided_by
        coverage.updated_at = datetime.now()
        session.add(coverage)
        session.add(
            EquipmentWarrantyDecision(
                coverage_id=coverage_id,
                action=normalized_action,
                reason=cleaned_reason,
                decided_by=decided_by,
            )
        )
        await session.commit()
        await session.refresh(coverage)
        return cls.to_item(coverage)

    @classmethod
    async def recalculate_after_maintenance(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        event_type: EquipmentServiceEventType,
        event_date: datetime,
    ) -> None:
        if event_type != EquipmentServiceEventType.MAINTENANCE:
            return
        normalized_event_date = cls._naive(event_date) or datetime.now()
        await cls._resolve_open_maintenance_reminders(
            session,
            equipment_id=equipment_id,
            resolved_at=normalized_event_date,
        )
        result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == equipment_id,
                EquipmentWarrantyCoverage.maintenance_required == True,
            )
        )
        for coverage in result.scalars().all():
            if coverage.maintenance_interval_months:
                coverage.next_maintenance_due_at = cls._add_months(
                    normalized_event_date,
                    int(coverage.maintenance_interval_months),
                )
                coverage.updated_at = datetime.now()
                session.add(coverage)
