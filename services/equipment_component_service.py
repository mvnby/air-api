from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import EquipmentComponent
from models.tenancy import TenantScope
from services.equipment_service import EquipmentService


class EquipmentComponentService:
    @staticmethod
    async def list_components(
        session: AsyncSession,
        *,
        equipment_id: int,
        include_archived: bool = False,
        tenant_scope: TenantScope,
    ) -> list[Dict[str, Any]]:
        if not await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        ):
            return []
        filters = [EquipmentComponent.equipment_id == equipment_id]
        if not include_archived:
            filters.append(EquipmentComponent.is_archived == False)
        result = await session.execute(
            select(EquipmentComponent)
            .where(*filters)
            .order_by(
                EquipmentComponent.is_archived.asc(),
                EquipmentComponent.component_type.asc(),
                EquipmentComponent.id.asc(),
            )
        )
        return [EquipmentService._to_component_item(item) for item in result.scalars().all()]

    @staticmethod
    async def create_component(
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

        catalog_product_id = payload.get("catalog_product_id")
        if catalog_product_id is not None:
            await EquipmentService._ensure_product_exists(session, int(catalog_product_id))
        supplier_id = payload.get("supplier_id")
        if supplier_id is not None:
            await EquipmentService._ensure_supplier_exists(session, int(supplier_id))

        component = EquipmentComponent(
            equipment_id=equipment_id,
            catalog_product_id=int(catalog_product_id) if catalog_product_id is not None else None,
            supplier_id=int(supplier_id) if supplier_id is not None else None,
            **EquipmentService._component_values_from_payload(payload),
            is_archived=bool(payload.get("is_archived", False)),
        )
        session.add(component)
        await session.commit()
        await session.refresh(component)
        return EquipmentService._to_component_item(component)
    @staticmethod
    async def update_component(
        session: AsyncSession,
        *,
        equipment_id: int,
        component_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        if not await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        ):
            return None
        component = await EquipmentService._get_equipment_component(
            session,
            equipment_id=equipment_id,
            component_id=component_id,
        )
        if not component:
            return None

        if "catalog_product_id" in payload:
            catalog_product_id = payload.get("catalog_product_id")
            if catalog_product_id is None:
                component.catalog_product_id = None
            else:
                await EquipmentService._ensure_product_exists(session, int(catalog_product_id))
                component.catalog_product_id = int(catalog_product_id)

        if "supplier_id" in payload:
            supplier_id = payload.get("supplier_id")
            if supplier_id is None:
                component.supplier_id = None
            else:
                await EquipmentService._ensure_supplier_exists(session, int(supplier_id))
                component.supplier_id = int(supplier_id)

        text_fields = (
            "component_type",
            "title",
            "brand",
            "model",
            "serial",
            "inventory_number",
            "supplier_invoice_number",
            "notes",
        )
        for field in text_fields:
            if field not in payload:
                continue
            value = EquipmentService._clean_optional_text(payload.get(field))
            if field == "component_type":
                component.component_type = EquipmentService._normalize_component_type(value)
            else:
                setattr(component, field, value)
        if "supplier_invoice_date" in payload:
            component.supplier_invoice_date = EquipmentService._normalize_naive_datetime(
                payload.get("supplier_invoice_date")
            )
        if "is_archived" in payload and payload["is_archived"] is not None:
            component.is_archived = bool(payload["is_archived"])

        component.updated_at = datetime.now()
        session.add(component)
        await session.commit()
        await session.refresh(component)
        return EquipmentService._to_component_item(component)
