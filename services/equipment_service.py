from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerEquipment,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    Order,
)


class EquipmentService:
    TRUE_VALUES = {"1", "true", "yes", "y", "да", "д", "истина"}
    FALSE_VALUES = {"0", "false", "no", "n", "нет", "н", "ложь"}
    REPAIR_HISTORY_AUTO_SYNC_STATUSES = frozenset({"completed", "not_repairable"})

    @staticmethod
    def _clean_optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None

    @staticmethod
    def _normalize_event_type(raw: Any, fallback: EquipmentServiceEventType = EquipmentServiceEventType.OTHER) -> EquipmentServiceEventType:
        if isinstance(raw, EquipmentServiceEventType):
            return raw
        value = EquipmentService._clean_optional_text(raw)
        if not value:
            return fallback
        try:
            return EquipmentServiceEventType(value)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in EquipmentServiceEventType)
            raise ValueError(f"Invalid service history event_type: {raw}. Allowed: {allowed}") from exc

    @staticmethod
    def _enum_value(raw: Any) -> str:
        return raw.value if hasattr(raw, "value") else str(raw)

    @staticmethod
    def _normalize_naive_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is not None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def _boolish(raw: Any) -> Optional[bool]:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return raw
        value = str(raw).strip().casefold()
        if value in EquipmentService.TRUE_VALUES:
            return True
        if value in EquipmentService.FALSE_VALUES:
            return False
        return None

    @staticmethod
    def _first_text(*values: Any) -> Optional[str]:
        for value in values:
            cleaned = EquipmentService._clean_optional_text(value)
            if cleaned:
                return cleaned
        return None

    @staticmethod
    def is_repair_order_history_sync_eligible(order: Order) -> bool:
        """Policy for future automation: only terminal repair milestones may sync automatically."""
        from services.order_service import OrderService

        workflow_type = OrderService._normalize_workflow_type(getattr(order, "workflow_type", None))
        if workflow_type != "repair":
            return False

        repair_meta = OrderService._get_repair_meta(order)
        try:
            status = OrderService.normalize_repair_status(
                repair_meta.get(OrderService.REPAIR_STATUS_KEY),
                fallback=OrderService.REPAIR_DEFAULT_STATUS,
            )
        except ValueError:
            return False
        return status in EquipmentService.REPAIR_HISTORY_AUTO_SYNC_STATUSES

    @staticmethod
    def _default_display_name(data: Dict[str, Any]) -> Optional[str]:
        explicit = EquipmentService._clean_optional_text(data.get("display_name"))
        if explicit:
            return explicit

        parts = [
            EquipmentService._clean_optional_text(data.get("brand")),
            EquipmentService._clean_optional_text(data.get("model")),
            EquipmentService._clean_optional_text(data.get("serial")),
        ]
        label = " ".join(part for part in parts if part)
        if label:
            return label
        return EquipmentService._clean_optional_text(data.get("equipment_type")) or "HVAC equipment"

    @staticmethod
    def _to_equipment_item(equipment: CustomerEquipment) -> Dict[str, Any]:
        return {
            "id": int(equipment.id or 0),
            "customer_id": int(equipment.customer_id),
            "customer_branch_id": equipment.customer_branch_id,
            "equipment_type": equipment.equipment_type,
            "display_name": equipment.display_name,
            "brand": equipment.brand,
            "model": equipment.model,
            "serial": equipment.serial,
            "inventory_number": equipment.inventory_number,
            "location_hint": equipment.location_hint,
            "refrigerant_type": equipment.refrigerant_type,
            "notes": equipment.notes,
            "is_archived": bool(equipment.is_archived),
            "created_at": equipment.created_at,
            "updated_at": equipment.updated_at,
        }

    @staticmethod
    def _to_history_item(entry: EquipmentServiceHistory) -> Dict[str, Any]:
        return {
            "id": int(entry.id or 0),
            "equipment_id": int(entry.equipment_id),
            "order_id": entry.order_id,
            "event_type": EquipmentService._enum_value(entry.event_type),
            "event_date": entry.event_date,
            "complaint_snapshot": entry.complaint_snapshot,
            "diagnostic_result": entry.diagnostic_result,
            "repair_recommendation": entry.repair_recommendation,
            "refrigerant_type": entry.refrigerant_type,
            "refrigerant_amount": entry.refrigerant_amount,
            "not_repairable": bool(entry.not_repairable),
            "not_repairable_reason": entry.not_repairable_reason,
            "notes": entry.notes,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    @staticmethod
    def _history_values_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        order_id = payload.get("order_id")
        return {
            "order_id": int(order_id) if order_id is not None else None,
            "event_type": EquipmentService._normalize_event_type(payload.get("event_type")),
            "event_date": EquipmentService._normalize_naive_datetime(payload.get("event_date")) or datetime.now(),
            "complaint_snapshot": EquipmentService._clean_optional_text(payload.get("complaint_snapshot")),
            "diagnostic_result": EquipmentService._clean_optional_text(payload.get("diagnostic_result")),
            "repair_recommendation": EquipmentService._clean_optional_text(payload.get("repair_recommendation")),
            "refrigerant_type": EquipmentService._clean_optional_text(payload.get("refrigerant_type")),
            "refrigerant_amount": EquipmentService._clean_optional_text(payload.get("refrigerant_amount")),
            "not_repairable": bool(payload.get("not_repairable", False)),
            "not_repairable_reason": EquipmentService._clean_optional_text(payload.get("not_repairable_reason")),
            "notes": EquipmentService._clean_optional_text(payload.get("notes")),
        }

    @staticmethod
    def _build_history_entry(*, equipment_id: int, payload: Dict[str, Any]) -> EquipmentServiceHistory:
        return EquipmentServiceHistory(
            equipment_id=equipment_id,
            **EquipmentService._history_values_from_payload(payload),
        )

    @staticmethod
    def _history_value_matches(entry: EquipmentServiceHistory, field: str, value: Any) -> bool:
        current = getattr(entry, field)
        if field == "event_type":
            return EquipmentService._enum_value(current) == EquipmentService._enum_value(value)
        return current == value

    @staticmethod
    def _apply_history_payload(entry: EquipmentServiceHistory, payload: Dict[str, Any]) -> bool:
        changed = False
        for field, value in EquipmentService._history_values_from_payload(payload).items():
            if EquipmentService._history_value_matches(entry, field, value):
                continue
            setattr(entry, field, value)
            changed = True
        if changed:
            entry.updated_at = datetime.now()
        return changed

    @staticmethod
    def resolve_repair_order_history_sync_target(
        existing_histories: list[EquipmentServiceHistory],
        *,
        equipment_id: int,
        order_id: int,
    ) -> Optional[EquipmentServiceHistory]:
        """Idempotency policy for explicit repair-order -> equipment-history sync."""
        histories = [
            item
            for item in existing_histories
            if item.order_id is not None and int(item.order_id) == int(order_id)
        ]
        if not histories:
            return None

        if len(histories) > 1:
            raise ValueError(f"Multiple equipment service history rows already exist for order #{order_id}")

        existing = histories[0]
        if int(existing.equipment_id) != int(equipment_id):
            raise ValueError(
                f"Equipment service history for order #{order_id} already belongs to "
                f"equipment #{existing.equipment_id}"
            )
        return existing

    @staticmethod
    def _preserve_omitted_repair_history_overrides(
        entry: EquipmentServiceHistory,
        history_payload: Dict[str, Any],
        request_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        preserved_payload = dict(history_payload)
        if "event_type" not in request_payload:
            preserved_payload["event_type"] = entry.event_type
        if "event_date" not in request_payload:
            preserved_payload["event_date"] = entry.event_date
        if "notes" not in request_payload:
            preserved_payload["notes"] = entry.notes
        return preserved_payload

    @staticmethod
    async def _ensure_customer_exists(session: AsyncSession, customer_id: int) -> Optional[Customer]:
        return await session.get(Customer, customer_id)

    @staticmethod
    async def _ensure_branch_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        customer_branch_id: int,
    ) -> CustomerBranch:
        branch = await session.get(CustomerBranch, customer_branch_id)
        if not branch:
            raise ValueError("Customer branch not found")
        if int(branch.customer_id) != int(customer_id):
            raise ValueError("Customer branch does not belong to selected customer")
        return branch

    @staticmethod
    async def _get_equipment(session: AsyncSession, equipment_id: int) -> Optional[CustomerEquipment]:
        result = await session.execute(select(CustomerEquipment).where(CustomerEquipment.id == equipment_id))
        return result.scalars().first()

    @staticmethod
    async def _validate_order_link(
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        order_id: int,
    ) -> Order:
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")
        if order.customer_id is None:
            raise ValueError("Order customer is required to link equipment service history")
        if int(order.customer_id) != int(equipment.customer_id):
            raise ValueError("Order customer does not match equipment customer")
        if (
            order.customer_branch_id is not None
            and equipment.customer_branch_id is not None
            and int(order.customer_branch_id) != int(equipment.customer_branch_id)
        ):
            raise ValueError("Order branch does not match equipment branch")
        return order

    @staticmethod
    async def list_equipment(
        session: AsyncSession,
        *,
        customer_id: Optional[int],
        customer_branch_id: Optional[int],
        page: int,
        limit: int,
        include_archived: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if customer_id is not None and not await EquipmentService._ensure_customer_exists(session, customer_id):
            return None
        if customer_id is not None and customer_branch_id is not None:
            await EquipmentService._ensure_branch_for_customer(
                session,
                customer_id=customer_id,
                customer_branch_id=customer_branch_id,
            )

        filters = []
        if customer_id is not None:
            filters.append(CustomerEquipment.customer_id == customer_id)
        if customer_branch_id is not None:
            filters.append(CustomerEquipment.customer_branch_id == customer_branch_id)
        if not include_archived:
            filters.append(CustomerEquipment.is_archived == False)

        count_result = await session.execute(select(func.count(CustomerEquipment.id)).where(*filters))
        total = int(count_result.scalar() or 0)
        result = await session.execute(
            select(CustomerEquipment)
            .where(*filters)
            .order_by(CustomerEquipment.is_archived.asc(), CustomerEquipment.created_at.desc(), CustomerEquipment.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        items = [EquipmentService._to_equipment_item(item) for item in result.scalars().all()]
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
    async def get_equipment_detail(
        session: AsyncSession,
        *,
        equipment_id: int,
        history_limit: int,
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(session, equipment_id)
        if not equipment:
            return None
        history = await EquipmentService.list_history(
            session,
            equipment_id=equipment_id,
            page=1,
            limit=history_limit,
        )
        data = EquipmentService._to_equipment_item(equipment)
        data["recent_history"] = history["items"]
        return data

    @staticmethod
    async def create_equipment(
        session: AsyncSession,
        *,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        customer_id = int(payload["customer_id"])
        if not await EquipmentService._ensure_customer_exists(session, customer_id):
            return None
        customer_branch_id = payload.get("customer_branch_id")
        if customer_branch_id is not None:
            await EquipmentService._ensure_branch_for_customer(
                session,
                customer_id=customer_id,
                customer_branch_id=int(customer_branch_id),
            )

        data = {
            "equipment_type": EquipmentService._clean_optional_text(payload.get("equipment_type")) or "hvac",
            "display_name": EquipmentService._clean_optional_text(payload.get("display_name")),
            "brand": EquipmentService._clean_optional_text(payload.get("brand")),
            "model": EquipmentService._clean_optional_text(payload.get("model")),
            "serial": EquipmentService._clean_optional_text(payload.get("serial")),
            "inventory_number": EquipmentService._clean_optional_text(payload.get("inventory_number")),
            "location_hint": EquipmentService._clean_optional_text(payload.get("location_hint")),
            "refrigerant_type": EquipmentService._clean_optional_text(payload.get("refrigerant_type")),
            "notes": EquipmentService._clean_optional_text(payload.get("notes")),
        }
        data["display_name"] = EquipmentService._default_display_name(data)
        equipment = CustomerEquipment(
            customer_id=customer_id,
            customer_branch_id=int(customer_branch_id) if customer_branch_id is not None else None,
            **data,
            is_archived=bool(payload.get("is_archived", False)),
        )
        session.add(equipment)
        await session.commit()
        await session.refresh(equipment)
        return EquipmentService._to_equipment_item(equipment)

    @staticmethod
    async def update_equipment(
        session: AsyncSession,
        *,
        equipment_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(session, equipment_id)
        if not equipment:
            return None

        if "customer_branch_id" in payload:
            customer_branch_id = payload.get("customer_branch_id")
            if customer_branch_id is None:
                equipment.customer_branch_id = None
            else:
                await EquipmentService._ensure_branch_for_customer(
                    session,
                    customer_id=int(equipment.customer_id),
                    customer_branch_id=int(customer_branch_id),
                )
                equipment.customer_branch_id = int(customer_branch_id)

        text_fields = (
            "equipment_type",
            "display_name",
            "brand",
            "model",
            "serial",
            "inventory_number",
            "location_hint",
            "refrigerant_type",
            "notes",
        )
        for field in text_fields:
            if field not in payload:
                continue
            value = EquipmentService._clean_optional_text(payload.get(field))
            if field == "equipment_type":
                equipment.equipment_type = value or "hvac"
            else:
                setattr(equipment, field, value)
        if "is_archived" in payload and payload["is_archived"] is not None:
            equipment.is_archived = bool(payload["is_archived"])

        equipment.updated_at = datetime.now()
        session.add(equipment)
        await session.commit()
        await session.refresh(equipment)
        return EquipmentService._to_equipment_item(equipment)

    @staticmethod
    async def list_history(
        session: AsyncSession,
        *,
        equipment_id: int,
        page: int,
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        if not await EquipmentService._get_equipment(session, equipment_id):
            return None

        count_result = await session.execute(
            select(func.count(EquipmentServiceHistory.id)).where(EquipmentServiceHistory.equipment_id == equipment_id)
        )
        total = int(count_result.scalar() or 0)
        result = await session.execute(
            select(EquipmentServiceHistory)
            .where(EquipmentServiceHistory.equipment_id == equipment_id)
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
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(session, equipment_id)
        if not equipment:
            return None

        order_id = payload.get("order_id")
        if order_id is not None:
            await EquipmentService._validate_order_link(
                session,
                equipment=equipment,
                order_id=int(order_id),
            )

        event_type = EquipmentService._normalize_event_type(payload.get("event_type"))
        entry = EquipmentService._build_history_entry(
            equipment_id=equipment_id,
            payload={**payload, "event_type": event_type},
        )
        session.add(entry)
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
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(session, equipment_id)
        if not equipment:
            return None
        order = await EquipmentService._validate_order_link(
            session,
            equipment=equipment,
            order_id=int(payload["order_id"]),
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
