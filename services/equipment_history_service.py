from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Customer, EquipmentServiceEventType, EquipmentServiceHistory, Order
from models.tenancy import TenantScope
from services.equipment_service import EquipmentService
from services.tenant_entity_access_service import TenantEntityAccessService


class EquipmentHistoryService:
    @staticmethod
    async def list_history(
        session: AsyncSession,
        *,
        equipment_id: int,
        page: int,
        limit: int,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        if not await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        ):
            return None

        history_scope = or_(
            EquipmentServiceHistory.order_id.is_(None),
            and_(
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            ),
        )
        count_result = await session.execute(
            select(func.count(EquipmentServiceHistory.id))
            .outerjoin(Order, Order.id == EquipmentServiceHistory.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                EquipmentServiceHistory.equipment_id == equipment_id,
                history_scope,
            )
        )
        total = int(count_result.scalar() or 0)
        result = await session.execute(
            select(EquipmentServiceHistory)
            .outerjoin(Order, Order.id == EquipmentServiceHistory.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                EquipmentServiceHistory.equipment_id == equipment_id,
                history_scope,
            )
            .options(selectinload(EquipmentServiceHistory.order))
            .order_by(EquipmentServiceHistory.event_date.desc(), EquipmentServiceHistory.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        items = [EquipmentService._to_history_item(item) for item in result.scalars().all()]
        return {
            "items": items,
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit else 0,
            },
        }

    @staticmethod
    async def _lock_order_for_history_sync(session: AsyncSession, *, order_id: int) -> None:
        await session.execute(select(Order.id).where(Order.id == order_id).with_for_update())

    @staticmethod
    async def _list_history_for_order(session: AsyncSession, *, order_id: int) -> list[EquipmentServiceHistory]:
        result = await session.execute(
            select(EquipmentServiceHistory)
            .where(EquipmentServiceHistory.order_id == order_id)
            .order_by(EquipmentServiceHistory.id.asc())
            .with_for_update()
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_history(
        session: AsyncSession,
        *,
        equipment_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if not equipment:
            return None

        order_id = payload.get("order_id")
        if order_id is not None:
            await EquipmentService._validate_order_link(
                session,
                equipment=equipment,
                order_id=int(order_id),
                tenant_scope=tenant_scope,
            )

        event_type = EquipmentService._normalize_event_type(payload.get("event_type"))
        entry = EquipmentService._build_history_entry(
            equipment_id=equipment_id,
            payload={**payload, "event_type": event_type},
        )
        session.add(entry)
        await session.flush()
        from services.warranty_service import WarrantyService

        await WarrantyService.recalculate_after_maintenance(
            session,
            equipment_id=equipment_id,
            event_type=event_type,
            event_date=entry.event_date,
            maintenance_provider=entry.maintenance_provider,
        )
        await session.commit()
        await session.refresh(entry)
        return EquipmentService._to_history_item(entry)
    @staticmethod
    def _infer_repair_history_event_type(repair_meta: Dict[str, Any]) -> EquipmentServiceEventType:
        status = EquipmentService._clean_optional_text(repair_meta.get("repair_status"))
        repair_not_viable = EquipmentService._boolish(repair_meta.get("repair_not_viable"))
        repair_possible = EquipmentService._boolish(repair_meta.get("repair_possible"))
        if status == "not_repairable" or repair_not_viable is True or repair_possible is False:
            return EquipmentServiceEventType.NOT_REPAIRABLE
        if status in {"completed", "repair_in_progress", "approved_for_repair", "awaiting_parts"}:
            return EquipmentServiceEventType.REPAIR
        if EquipmentService._first_text(repair_meta.get("refrigerant_type"), repair_meta.get("refrigerant_amount")):
            return EquipmentServiceEventType.REFRIGERANT_CHARGE
        if EquipmentService._first_text(repair_meta.get("diagnostic_result"), repair_meta.get("technical_condition")):
            return EquipmentServiceEventType.DIAGNOSTIC
        if EquipmentService._first_text(repair_meta.get("repair_recommendation"), repair_meta.get("technical_conclusion")):
            return EquipmentServiceEventType.RECOMMENDATION
        return EquipmentServiceEventType.OTHER

    @staticmethod
    def build_history_payload_from_repair_order(
        order: Order,
        *,
        event_type: Optional[Any] = None,
        event_date: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        from services.order_service import OrderService

        workflow_type = OrderService._normalize_workflow_type(getattr(order, "workflow_type", None))
        if workflow_type != "repair":
            raise ValueError("Only repair orders can create equipment service history from repair meta")

        repair_meta = OrderService._get_repair_meta(order)
        normalized_event_type = (
            EquipmentService._normalize_event_type(event_type)
            if event_type is not None
            else EquipmentService._infer_repair_history_event_type(repair_meta)
        )
        repair_not_viable = EquipmentService._boolish(repair_meta.get("repair_not_viable"))
        repair_possible = EquipmentService._boolish(repair_meta.get("repair_possible"))
        not_repairable = (
            normalized_event_type == EquipmentServiceEventType.NOT_REPAIRABLE
            or repair_not_viable is True
            or repair_possible is False
        )

        return {
            "order_id": int(order.id) if order.id is not None else None,
            "event_type": normalized_event_type,
            "event_date": (
                EquipmentService._normalize_naive_datetime(event_date)
                or EquipmentService._normalize_naive_datetime(order.closed_at)
                or EquipmentService._normalize_naive_datetime(order.updated_at)
                or datetime.now()
            ),
            "complaint_snapshot": EquipmentService._first_text(
                repair_meta.get("customer_complaint"),
                repair_meta.get("complaint_official"),
                repair_meta.get("complaint_text"),
                order.comment,
            ),
            "diagnostic_result": EquipmentService._first_text(
                repair_meta.get("diagnostic_result"),
                repair_meta.get("technical_condition"),
                repair_meta.get("defect_technical_condition"),
                repair_meta.get("measurement_result"),
            ),
            "repair_recommendation": EquipmentService._first_text(
                repair_meta.get("repair_recommendation"),
                repair_meta.get("recommended_decision"),
                repair_meta.get("technical_conclusion"),
            ),
            "refrigerant_type": EquipmentService._clean_optional_text(repair_meta.get("refrigerant_type")),
            "refrigerant_amount": EquipmentService._clean_optional_text(repair_meta.get("refrigerant_amount")),
            "not_repairable": not_repairable,
            "not_repairable_reason": EquipmentService._clean_optional_text(repair_meta.get("repair_not_viable_reason")),
            "notes": EquipmentService._first_text(
                notes,
                repair_meta.get("repair_completion_note"),
                repair_meta.get("customer_approval_note"),
                repair_meta.get("parts_note"),
            ),
        }

    @staticmethod
    async def add_history_from_repair_order(
        session: AsyncSession,
        *,
        equipment_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if not equipment:
            return None
        order = await EquipmentService._validate_order_link(
            session,
            equipment=equipment,
            order_id=int(payload["order_id"]),
            tenant_scope=tenant_scope,
        )
        order_id = int(order.id)
        await EquipmentService._lock_order_for_history_sync(session, order_id=order_id)
        existing_histories = await EquipmentService._list_history_for_order(session, order_id=order_id)
        existing_history = EquipmentService.resolve_repair_order_history_sync_target(
            existing_histories,
            equipment_id=equipment_id,
            order_id=order_id,
        )
        history_payload = EquipmentService.build_history_payload_from_repair_order(
            order,
            event_type=payload.get("event_type"),
            event_date=payload.get("event_date"),
            notes=payload.get("notes"),
        )
        if existing_history is not None:
            history_payload = EquipmentService._preserve_omitted_repair_history_overrides(
                existing_history,
                history_payload,
                payload,
            )
            if EquipmentService._apply_history_payload(existing_history, history_payload):
                session.add(existing_history)
                await session.commit()
                await session.refresh(existing_history)
            return EquipmentService._to_history_item(existing_history)

        entry = EquipmentService._build_history_entry(equipment_id=equipment_id, payload=history_payload)
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return EquipmentService._to_history_item(entry)
