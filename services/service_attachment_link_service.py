"""Validation helpers for attachment links to orders and equipment history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CustomerEquipment,
    EquipmentComponent,
    EquipmentAttachmentLink,
    EquipmentServiceHistory,
    Order,
    OrderAttachmentLink,
    OrderWorkStage,
)


@dataclass(frozen=True)
class AttachmentLinkContext:
    equipment: CustomerEquipment | None
    component_id: int | None
    service_history_id: int | None


class ServiceAttachmentLinkService:
    @staticmethod
    async def validate_order_context(
        session: AsyncSession,
        *,
        order: Order,
        work_stage_id: int | None = None,
        equipment_id: int | None = None,
        component_id: int | None = None,
        service_history_id: int | None = None,
    ) -> AttachmentLinkContext:
        order_id = int(order.id or 0)
        if work_stage_id is not None:
            stage = await session.get(OrderWorkStage, work_stage_id)
            if not stage or int(stage.order_id) != order_id:
                raise ValueError("Work stage does not belong to this order")

        history = None
        if service_history_id is not None:
            history = await session.get(EquipmentServiceHistory, service_history_id)
            if not history:
                raise ValueError("Equipment service history event not found")
            if history.order_id is not None and int(history.order_id) != order_id:
                raise ValueError("Equipment service history event does not belong to this order")
            if equipment_id is None:
                equipment_id = int(history.equipment_id)
            elif int(history.equipment_id) != int(equipment_id):
                raise ValueError("Equipment service history event does not belong to this equipment")

        equipment = None
        if equipment_id is not None:
            equipment = await session.get(CustomerEquipment, int(equipment_id))
            if not equipment:
                raise ValueError("Equipment not found")
            if order.customer_id is None or int(equipment.customer_id) != int(order.customer_id):
                raise ValueError("Equipment does not belong to the order customer")
            if (
                order.customer_branch_id is not None
                and equipment.customer_branch_id is not None
                and int(order.customer_branch_id) != int(equipment.customer_branch_id)
            ):
                raise ValueError("Equipment does not belong to the order branch")

        if component_id is not None:
            component = await session.get(EquipmentComponent, int(component_id))
            if not component or equipment is None or int(component.equipment_id) != int(equipment.id or 0):
                raise ValueError("Equipment component does not belong to this equipment")

        return AttachmentLinkContext(
            equipment=equipment,
            component_id=int(component_id) if component_id is not None else None,
            service_history_id=int(service_history_id) if service_history_id is not None else None,
        )

    @classmethod
    async def replace_equipment_link(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        order_link: OrderAttachmentLink,
        attachment_id: int,
        payload: dict,
    ) -> EquipmentAttachmentLink | None:
        result = await session.execute(
            select(EquipmentAttachmentLink).where(
                EquipmentAttachmentLink.order_attachment_link_id == int(order_link.id or 0),
                EquipmentAttachmentLink.archived_at.is_(None),
            )
        )
        active_links = list(result.scalars().all())
        current = active_links[0] if active_links else None
        equipment_id = payload.get("equipment_id") if "equipment_id" in payload else (
            current.equipment_id if current else None
        )
        component_id = payload.get("component_id") if "component_id" in payload else (
            current.component_id if current and current.equipment_id == equipment_id else None
        )
        service_history_id = payload.get("service_history_id") if "service_history_id" in payload else (
            current.service_history_id if current and current.equipment_id == equipment_id else None
        )
        if "equipment_id" in payload and equipment_id is None and (
            component_id is not None or service_history_id is not None
        ):
            raise ValueError("Component and service history must be cleared when equipment is unlinked")

        context = await cls.validate_order_context(
            session,
            order=order,
            equipment_id=int(equipment_id) if equipment_id is not None else None,
            component_id=int(component_id) if component_id is not None else None,
            service_history_id=int(service_history_id) if service_history_id is not None else None,
        )
        if context.equipment is None:
            for item in active_links:
                item.archived_at = datetime.now()
                session.add(item)
            return None

        normalized_equipment_id = int(context.equipment.id or 0)
        target = next(
            (item for item in active_links if int(item.equipment_id) == normalized_equipment_id),
            None,
        )
        if target is None:
            target = EquipmentAttachmentLink(
                equipment_id=normalized_equipment_id,
                attachment_id=attachment_id,
                order_attachment_link_id=int(order_link.id or 0),
            )
        target.archived_at = None
        target.component_id = context.component_id
        target.service_history_id = context.service_history_id
        target.category = order_link.category
        target.caption = order_link.caption
        session.add(target)
        for item in active_links:
            if item is not target:
                item.archived_at = datetime.now()
                session.add(item)
        return target
