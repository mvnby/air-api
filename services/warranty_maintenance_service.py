"""Validated maintenance transitions for equipment warranty coverages."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    EquipmentMaintenanceReminder,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
)


class WarrantyMaintenanceService:
    REMINDER_THRESHOLDS = {
        "due_30_days": timedelta(days=30),
        "due_7_days": timedelta(days=7),
    }
    EVENT_PROVIDERS = {"mvn", "authorized", "external"}

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        from services.equipment_service import EquipmentService

        return EquipmentService._add_months(value, months)

    @classmethod
    def _provider_is_allowed(cls, *, actual: str | None, required: str) -> bool:
        if actual not in cls.EVENT_PROVIDERS:
            return False
        if required == "any":
            return True
        return actual == required

    @staticmethod
    async def _resolve_cycle_reminders(
        session: AsyncSession,
        *,
        coverage_id: int,
        due_at: datetime | None,
        resolved_at: datetime,
    ) -> None:
        filters = [
            EquipmentMaintenanceReminder.coverage_id == coverage_id,
            EquipmentMaintenanceReminder.status == "open",
        ]
        if due_at is not None:
            filters.append(EquipmentMaintenanceReminder.due_at == due_at)
        result = await session.execute(select(EquipmentMaintenanceReminder).where(*filters))
        for reminder in result.scalars().all():
            reminder.status = "resolved"
            reminder.resolved_at = resolved_at
            session.add(reminder)

    @classmethod
    async def apply_maintenance_event(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        event_type: EquipmentServiceEventType,
        event_date: datetime,
        maintenance_provider: str | None,
        coverage_id: int | None = None,
        allow_overdue: bool = False,
    ) -> dict[str, int]:
        if event_type != EquipmentServiceEventType.MAINTENANCE:
            return {"advanced": 0, "skipped": 0}
        normalized_event_date = cls._naive(event_date) or datetime.now()
        filters = [
            EquipmentWarrantyCoverage.equipment_id == equipment_id,
            EquipmentWarrantyCoverage.maintenance_required == True,
        ]
        if coverage_id is not None:
            filters.append(EquipmentWarrantyCoverage.id == coverage_id)
        result = await session.execute(select(EquipmentWarrantyCoverage).where(*filters))
        advanced = 0
        skipped = 0
        for coverage in result.scalars().all():
            interval = int(coverage.maintenance_interval_months or 0)
            if interval <= 0 or coverage.decision_status == "voided":
                skipped += 1
                continue
            if not cls._provider_is_allowed(
                actual=maintenance_provider,
                required=coverage.allowed_maintenance_provider or "any",
            ):
                skipped += 1
                continue
            starts_at = cls._naive(coverage.starts_at)
            if starts_at is not None and normalized_event_date < starts_at:
                skipped += 1
                continue
            due_at = cls._naive(coverage.next_maintenance_due_at)
            candidate_next_due = cls._add_months(normalized_event_date, interval)
            if due_at is not None and candidate_next_due <= due_at:
                skipped += 1
                continue
            if due_at is not None:
                grace_until = due_at + timedelta(days=int(coverage.grace_period_days or 0))
                if normalized_event_date > grace_until and not allow_overdue:
                    skipped += 1
                    continue
            await cls._resolve_cycle_reminders(
                session,
                coverage_id=int(coverage.id or 0),
                due_at=due_at,
                resolved_at=normalized_event_date,
            )
            coverage.next_maintenance_due_at = candidate_next_due
            coverage.updated_at = datetime.now()
            session.add(coverage)
            advanced += 1
        return {"advanced": advanced, "skipped": skipped}

    @classmethod
    async def restore_from_latest_maintenance(
        cls,
        session: AsyncSession,
        *,
        coverage: EquipmentWarrantyCoverage,
    ) -> None:
        result = await session.execute(
            select(EquipmentServiceHistory)
            .where(
                EquipmentServiceHistory.equipment_id == coverage.equipment_id,
                EquipmentServiceHistory.event_type == EquipmentServiceEventType.MAINTENANCE,
                EquipmentServiceHistory.maintenance_provider.is_not(None),
            )
            .order_by(EquipmentServiceHistory.event_date.desc(), EquipmentServiceHistory.id.desc())
        )
        event = result.scalars().first()
        if not event:
            return
        await cls.apply_maintenance_event(
            session,
            equipment_id=int(coverage.equipment_id),
            coverage_id=int(coverage.id or 0),
            event_type=EquipmentServiceEventType.MAINTENANCE,
            event_date=event.event_date,
            maintenance_provider=event.maintenance_provider,
            allow_overdue=True,
        )

    @classmethod
    async def generate_reminders(
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
            reminder_times = {
                **{kind: due_at - threshold for kind, threshold in cls.REMINDER_THRESHOLDS.items()},
                "overdue": due_at + timedelta(days=int(coverage.grace_period_days or 0)),
            }
            for reminder_type, trigger_at in reminder_times.items():
                if reminder_type == "overdue":
                    if moment <= trigger_at:
                        continue
                elif moment < trigger_at:
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
