"""Independent preventive-maintenance plans for customer equipment."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Customer, CustomerEquipment, EquipmentServiceEventType, EquipmentServiceHistory
from models.tenancy import TenantScope
from services.tenant_scope_service import tenant_scope_clause


class EquipmentMaintenancePlanService:
    CALENDAR_COLOR = "#f59e0b"

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @classmethod
    def anchor_at(cls, equipment: CustomerEquipment) -> datetime | None:
        return cls._naive(
            equipment.maintenance_anchor_at
            or equipment.commissioned_at
            or equipment.installed_at
        )

    @classmethod
    def next_due_at(
        cls,
        equipment: CustomerEquipment,
        *,
        latest_maintenance_at: datetime | None,
    ) -> datetime | None:
        if not equipment.maintenance_enabled:
            return None
        anchor = cls.anchor_at(equipment)
        if anchor is None:
            return None
        latest = cls._naive(latest_maintenance_at)
        cycle_start = latest if latest is not None and latest >= anchor else anchor
        from services.equipment_service import EquipmentService

        return EquipmentService._add_months(
            cycle_start,
            int(equipment.maintenance_interval_months or 12),
        )

    @classmethod
    async def latest_maintenance_by_equipment(
        cls,
        session: AsyncSession,
        equipment_ids: Iterable[int],
    ) -> dict[int, datetime]:
        ids = [int(item) for item in equipment_ids]
        if not ids:
            return {}
        result = await session.execute(
            select(
                EquipmentServiceHistory.equipment_id,
                func.max(EquipmentServiceHistory.event_date),
            )
            .where(
                EquipmentServiceHistory.equipment_id.in_(ids),
                EquipmentServiceHistory.event_type == EquipmentServiceEventType.MAINTENANCE,
            )
            .group_by(EquipmentServiceHistory.equipment_id)
        )
        return {
            int(equipment_id): event_date
            for equipment_id, event_date in result.all()
            if event_date is not None
        }

    @classmethod
    async def calendar_events(
        cls,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
        tenant_scope: TenantScope,
        now: datetime | None = None,
    ) -> list[dict]:
        start = cls._naive(start_date)
        end = cls._naive(end_date)
        if start is None or end is None or start > end:
            raise ValueError("Calendar start date must not be after end date")
        moment = cls._naive(now) or datetime.now()
        today = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await session.execute(
            select(CustomerEquipment)
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .options(
                selectinload(CustomerEquipment.customer),
                selectinload(CustomerEquipment.customer_branch),
            )
            .where(
                tenant_scope_clause(Customer, tenant_scope),
                Customer.is_archived == False,
                CustomerEquipment.is_archived == False,
                CustomerEquipment.maintenance_enabled == True,
            )
        )
        equipment_rows = list(result.scalars().all())
        latest_by_equipment = await cls.latest_maintenance_by_equipment(
            session,
            [int(item.id or 0) for item in equipment_rows],
        )
        events = []
        for equipment in equipment_rows:
            equipment_id = int(equipment.id or 0)
            due_at = cls.next_due_at(
                equipment,
                latest_maintenance_at=latest_by_equipment.get(equipment_id),
            )
            if due_at is None:
                continue
            overdue = due_at.date() < moment.date()
            display_start = today if overdue else due_at
            if display_start < start or display_start > end:
                continue
            customer = equipment.customer
            branch = equipment.customer_branch
            equipment_title = equipment.display_name or equipment.model or f"Оборудование #{equipment_id}"
            events.append(
                {
                    "id": f"equipment-{equipment_id}-maintenance",
                    "order_id": None,
                    "equipment_id": equipment_id,
                    "type": "equipment_maintenance",
                    "date": due_at,
                    "status": "overdue" if overdue else "scheduled",
                    "customer_name": customer.name if customer else None,
                    "customer_phone": customer.phone if customer else None,
                    "address": (
                        branch.delivery_address
                        if branch
                        else equipment.location_hint
                        or (customer.actual_address if customer else None)
                        or (customer.legal_address if customer else None)
                    ),
                    "title": (
                        f"{'Просрочено ТО' if overdue else 'Предложить ТО'}: "
                        f"{customer.name} · {equipment_title}"
                        if customer
                        else f"{'Просрочено ТО' if overdue else 'Предложить ТО'}: {equipment_title}"
                    ),
                    "start": display_start,
                    "color": cls.CALENDAR_COLOR,
                }
            )
        return events
