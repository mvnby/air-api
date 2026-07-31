from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Customer, CustomerEquipment, EquipmentOrderLink, Order
from models.tenancy import TenantScope
from services.equipment_service import EquipmentService
from services.tenant_entity_access_service import TenantEntityAccessService


class EquipmentLinkService:
    @staticmethod
    async def list_for_order(
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            return None
        result = await session.execute(
            select(EquipmentOrderLink, CustomerEquipment)
            .join(CustomerEquipment, CustomerEquipment.id == EquipmentOrderLink.equipment_id)
            .where(
                EquipmentOrderLink.order_id == order_id,
                CustomerEquipment.is_archived == False,
            )
            .order_by(CustomerEquipment.created_at.desc(), CustomerEquipment.id.desc())
        )
        rows = list(result.all())
        seen_ids = {int(equipment.id or 0) for _, equipment in rows}

        legacy_result = await session.execute(
            select(CustomerEquipment)
            .where(
                CustomerEquipment.source_order_id == order_id,
                CustomerEquipment.is_archived == False,
            )
            .order_by(CustomerEquipment.created_at.desc(), CustomerEquipment.id.desc())
        )
        for equipment in legacy_result.scalars().all():
            if int(equipment.id or 0) not in seen_ids:
                rows.append((None, equipment))

        items = []
        for link, equipment in rows:
            detail = await EquipmentService.get_equipment_detail(
                session,
                equipment_id=int(equipment.id or 0),
                history_limit=3,
                tenant_scope=tenant_scope,
            )
            if detail:
                items.append(
                    {
                        "link_id": int(link.id or 0) if link else None,
                        "role": link.role if link else "sale",
                        "legacy_source_link": link is None,
                        "equipment": detail,
                    }
                )
        return {"items": items, "total": len(items)}

    @staticmethod
    async def link_existing(
        session: AsyncSession,
        *,
        order_id: int,
        equipment_id: int,
        role: str,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        equipment = await TenantEntityAccessService.get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if not order or not equipment:
            return None
        await EquipmentService._validate_order_link(
            session,
            equipment=equipment,
            order_id=order_id,
            tenant_scope=tenant_scope,
        )
        link = await EquipmentService._ensure_equipment_order_link(
            session,
            equipment_id=equipment_id,
            order_id=order_id,
            role=role,
        )
        await session.commit()
        detail = await EquipmentService.get_equipment_detail(
            session,
            equipment_id=equipment_id,
            history_limit=3,
            tenant_scope=tenant_scope,
        )
        return {
            "link_id": int(link.id or 0),
            "role": link.role,
            "legacy_source_link": False,
            "equipment": detail,
        }

    @staticmethod
    async def unlink(
        session: AsyncSession,
        *,
        order_id: int,
        link_id: int,
        tenant_scope: TenantScope,
    ) -> bool:
        if await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        ) is None:
            return False
        result = await session.execute(
            select(EquipmentOrderLink).where(
                EquipmentOrderLink.id == link_id,
                EquipmentOrderLink.order_id == order_id,
            )
        )
        link = result.scalars().first()
        if not link:
            return False
        equipment = await TenantEntityAccessService.get_equipment(
            session,
            link.equipment_id,
            tenant_scope=tenant_scope,
        )
        if equipment is None:
            return False
        if equipment and equipment.source_order_id == order_id:
            equipment.source_order_id = None
            session.add(equipment)
        await session.delete(link)
        await session.commit()
        return True

    @staticmethod
    async def list_linked_orders(
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]]:
        equipment = await TenantEntityAccessService.get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if equipment is None:
            return []
        result = await session.execute(
            select(EquipmentOrderLink, Order)
            .join(Order, Order.id == EquipmentOrderLink.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                EquipmentOrderLink.equipment_id == equipment_id,
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            )
            .options(selectinload(Order.customer))
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        items = []
        seen = set()
        for link, order in result.all():
            seen.add(int(order.id or 0))
            items.append(
                {
                    "order_id": int(order.id or 0),
                    "role": link.role,
                    "title": order.title or f"Заказ #{order.id}",
                    "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                    "created_at": order.created_at,
                }
            )
        if equipment and equipment.source_order_id and int(equipment.source_order_id) not in seen:
            order = await TenantEntityAccessService.get_order(
                session,
                int(equipment.source_order_id),
                tenant_scope=tenant_scope,
            )
            if order:
                items.append(
                    {
                        "order_id": int(order.id or 0),
                        "role": "sale",
                        "title": order.title or f"Заказ #{order.id}",
                        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                        "created_at": order.created_at,
                    }
                )
        return items
