from datetime import datetime, time
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from models import (
    CustomerEquipment,
    EquipmentComponent,
    Order,
    OrderInstaller,
    OrderProductLink,
    OrderStatus,
    OrderWorkStage,
    Product,
    StaffUser,
)
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.equipment_service import EquipmentService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService


class BotWarrantyNameplateService:
    UNIT_TYPES = {"indoor_unit", "outdoor_unit"}
    ORDER_WORKFLOWS = {"sales_installation", "service_work"}
    HISTORY_META_KEY = "warranty_nameplate_recognitions"
    WARRANTY_MONTHS_DEFAULT = 24

    FIELD_LABELS = {
        "brand": "Бренд",
        "model": "Модель блока",
        "serial": "Серийный номер",
        "refrigerant_type": "Хладагент",
    }
    UNIT_LABELS = {
        "indoor_unit": "внутренний блок",
        "outdoor_unit": "наружный блок",
    }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 500) -> Optional[str]:
        return BotRepairNameplateService._clean_text(value, max_length=max_length)

    @staticmethod
    def _today_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
        current = now or datetime.now()
        start = datetime.combine(current.date(), time.min)
        end = datetime.combine(current.date(), time.max)
        return start, end

    @classmethod
    def _is_installation_order(cls, order: Order | None) -> bool:
        if not order or order.status != OrderStatus.EXECUTION:
            return False
        workflow_type = OrderService._normalize_workflow_type(getattr(order, "workflow_type", None))
        return workflow_type in cls.ORDER_WORKFLOWS

    @classmethod
    def _map_order(cls, order: Order) -> dict[str, Any]:
        customer = getattr(order, "customer", None)
        return {
            "id": int(order.id or 0),
            "title": order.title,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "workflow_type": OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)),
            "customer_name": getattr(customer, "name", None) if customer else None,
            "customer_phone": getattr(customer, "phone", None) if customer else None,
            "address": order.delivery_address,
            "installation_date": order.installation_date,
            "updated_at": order.updated_at,
            "created_at": order.created_at,
        }

    @classmethod
    async def _legacy_installer_id(cls, session: AsyncSession, telegram_user_id: int | str | None) -> Optional[int]:
        try:
            normalized_telegram_id = int(telegram_user_id) if telegram_user_id is not None else 0
        except (TypeError, ValueError):
            return None
        if not normalized_telegram_id:
            return None

        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .where(StaffUser.status == StaffUserService.STATUS_ACTIVE)
            .order_by(StaffUser.id.asc())
            .limit(1)
        )
        staff = result.scalars().first()
        installer_id = getattr(staff, "legacy_installer_id", None)
        return int(installer_id) if installer_id else None

    @classmethod
    def _permission_filters(cls, installer_id: int):
        stage_exists = (
            select(OrderWorkStage.id)
            .where(OrderWorkStage.order_id == Order.id)
            .where(OrderWorkStage.installer_id == installer_id)
            .exists()
        )
        legacy_exists = (
            select(OrderInstaller.order_id)
            .where(OrderInstaller.order_id == Order.id)
            .where(OrderInstaller.installer_id == installer_id)
            .exists()
        )
        return or_(stage_exists, legacy_exists)

    @classmethod
    async def list_installation_orders(
        cls,
        session: AsyncSession,
        *,
        telegram_user_id: int | str | None,
        can_attach_any: bool = False,
        limit: int = 5,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        base_filters = [
            Order.status == OrderStatus.EXECUTION,
            Order.workflow_type.in_(sorted(cls.ORDER_WORKFLOWS)),
        ]
        if not can_attach_any:
            installer_id = await cls._legacy_installer_id(session, telegram_user_id)
            if not installer_id:
                return {"items": [], "scope": "today"}
            base_filters.append(cls._permission_filters(installer_id))

        capped_limit = max(1, min(limit, 10))
        start, end = cls._today_bounds(now)
        today_stmt = (
            select(Order)
            .where(*base_filters)
            .where(Order.installation_date >= start)
            .where(Order.installation_date <= end)
            .options(selectinload(Order.customer))
            .order_by(Order.installation_date.asc(), Order.updated_at.desc(), Order.id.desc())
            .limit(capped_limit)
        )
        today_result = await session.execute(today_stmt)
        today_orders = today_result.scalars().all()
        if today_orders:
            return {"items": [cls._map_order(order) for order in today_orders], "scope": "today"}

        fallback_stmt = (
            select(Order)
            .where(*base_filters)
            .options(selectinload(Order.customer))
            .order_by(Order.installation_date.desc().nullslast(), Order.updated_at.desc(), Order.id.desc())
            .limit(capped_limit)
        )
        fallback_result = await session.execute(fallback_stmt)
        return {"items": [cls._map_order(order) for order in fallback_result.scalars().all()], "scope": "execution"}

    @classmethod
    async def can_use_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        telegram_user_id: int | str | None,
        can_attach_any: bool = False,
    ) -> bool:
        result = await session.execute(select(Order).where(Order.id == order_id).limit(1))
        order = result.scalars().first()
        if not cls._is_installation_order(order):
            return False
        if can_attach_any:
            return True
        return await BotOrderAttachmentService.can_attach_to_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
        )

    @classmethod
    def _component_payload_from_extracted(cls, extracted: dict[str, Any]) -> dict[str, Any]:
        return {
            "brand": cls._clean_text(extracted.get("equipment_brand"), max_length=120),
            "model": cls._clean_text(extracted.get("equipment_model"), max_length=200),
            "serial": cls._clean_text(extracted.get("equipment_serial_number"), max_length=160),
            "refrigerant_type": cls._clean_text(extracted.get("refrigerant_type"), max_length=80),
        }

    @classmethod
    def _preview_component_merge(cls, component: EquipmentComponent | None, payload: dict[str, Any]) -> dict[str, Any]:
        applied: dict[str, Any] = {}
        conflicts: dict[str, dict[str, str]] = {}
        skipped: dict[str, Any] = {}
        for field in ("brand", "model", "serial"):
            candidate = cls._clean_text(payload.get(field), max_length=500)
            if not candidate:
                continue
            existing = cls._clean_text(getattr(component, field, None), max_length=500) if component else None
            if existing and existing != candidate:
                conflicts[field] = {"existing": existing, "candidate": candidate}
            elif existing == candidate:
                skipped[field] = candidate
            else:
                applied[field] = candidate
        return {"applied": applied, "conflicts": conflicts, "skipped": skipped}

    @classmethod
    def _preview_equipment_merge(cls, equipment: CustomerEquipment | None, payload: dict[str, Any]) -> dict[str, Any]:
        applied: dict[str, Any] = {}
        conflicts: dict[str, dict[str, str]] = {}
        skipped: dict[str, Any] = {}
        for field in ("brand", "refrigerant_type"):
            candidate = cls._clean_text(payload.get(field), max_length=500)
            if not candidate:
                continue
            existing = cls._clean_text(getattr(equipment, field, None), max_length=500) if equipment else None
            if existing and existing != candidate:
                conflicts[field] = {"existing": existing, "candidate": candidate}
            elif existing == candidate:
                skipped[field] = candidate
            else:
                applied[field] = candidate
        return {"applied": applied, "conflicts": conflicts, "skipped": skipped}

    @classmethod
    async def _load_order(cls, session: AsyncSession, order_id: int) -> Optional[Order]:
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product).selectinload(Product.brand),
            )
            .limit(1)
        )
        return result.scalars().first()

    @classmethod
    async def _existing_equipment_for_order(cls, session: AsyncSession, order_id: int) -> list[CustomerEquipment]:
        result = await session.execute(
            select(CustomerEquipment)
            .where(CustomerEquipment.source_order_id == order_id)
            .where(CustomerEquipment.is_archived == False)
            .order_by(CustomerEquipment.id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def _components_for_equipment(cls, session: AsyncSession, equipment_ids: list[int]) -> list[EquipmentComponent]:
        if not equipment_ids:
            return []
        result = await session.execute(
            select(EquipmentComponent)
            .where(EquipmentComponent.equipment_id.in_(equipment_ids))
            .where(EquipmentComponent.is_archived == False)
            .order_by(EquipmentComponent.equipment_id.asc(), EquipmentComponent.id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def _ensure_equipment_for_order(cls, session: AsyncSession, order: Order) -> list[CustomerEquipment]:
        order_id = int(order.id or 0)
        equipment = await cls._existing_equipment_for_order(session, order_id)
        if equipment:
            return equipment

        try:
            await EquipmentService.create_equipment_from_order(
                session,
                order_id=order_id,
                payload={
                    "warranty_months": cls.WARRANTY_MONTHS_DEFAULT,
                    "warranty_start_date": order.installation_date,
                    "include_component_placeholders": True,
                },
            )
        except ValueError:
            if order.customer_id is None:
                raise
            start = EquipmentService._order_warranty_start(order, {"warranty_start_date": order.installation_date})
            expires = EquipmentService._add_months(start, cls.WARRANTY_MONTHS_DEFAULT)
            fallback_equipment = CustomerEquipment(
                customer_id=int(order.customer_id),
                customer_branch_id=order.customer_branch_id,
                source_order_id=order_id,
                equipment_type="hvac",
                equipment_source="installed_by_us",
                display_name=cls._clean_text(order.title, max_length=200) or f"Оборудование из заказа #{order_id}",
                location_hint=cls._clean_text(
                    order.delivery_address or (order.customer_branch.delivery_address if order.customer_branch else None),
                    max_length=300,
                ),
                installed_at=EquipmentService._normalize_naive_datetime(order.installation_date),
                commissioned_at=start,
                warranty_started_at=start,
                warranty_expires_at=expires,
                warranty_terms="Гарантия действует при соблюдении условий эксплуатации и сервисного обслуживания.",
                notes=f"Создано ботом из заказа #{order_id} для заполнения гарантийного талона.",
            )
            session.add(fallback_equipment)
            await session.commit()
        return await cls._existing_equipment_for_order(session, order_id)

    @classmethod
    def _select_equipment_component(
        cls,
        equipment: list[CustomerEquipment],
        components: list[EquipmentComponent],
        *,
        unit_type: str,
        payload: dict[str, Any],
    ) -> tuple[CustomerEquipment | None, EquipmentComponent | None]:
        by_equipment_id = {int(item.id or 0): item for item in equipment}
        unit_components = [item for item in components if item.component_type == unit_type]
        serial = cls._clean_text(payload.get("serial"), max_length=160)
        model = cls._clean_text(payload.get("model"), max_length=200)
        for component in unit_components:
            if serial and cls._clean_text(component.serial, max_length=160) == serial:
                return by_equipment_id.get(int(component.equipment_id)), component
        for component in unit_components:
            if model and cls._clean_text(component.model, max_length=200) == model:
                return by_equipment_id.get(int(component.equipment_id)), component
        for component in unit_components:
            if not cls._clean_text(component.serial, max_length=160):
                return by_equipment_id.get(int(component.equipment_id)), component
        if unit_components:
            component = unit_components[0]
            return by_equipment_id.get(int(component.equipment_id)), component
        return (equipment[0] if equipment else None), None

    @classmethod
    async def build_merge_preview(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        unit_type: str,
        extracted: dict[str, Any],
    ) -> dict[str, Any] | None:
        if unit_type not in cls.UNIT_TYPES:
            raise ValueError("Неизвестный тип блока")
        order = await cls._load_order(session, order_id)
        if not cls._is_installation_order(order):
            return None
        equipment = await cls._existing_equipment_for_order(session, order_id)
        components = await cls._components_for_equipment(session, [int(item.id or 0) for item in equipment])
        payload = cls._component_payload_from_extracted(extracted)
        selected_equipment, selected_component = cls._select_equipment_component(
            equipment,
            components,
            unit_type=unit_type,
            payload=payload,
        )
        return {
            "unit_type": unit_type,
            "unit_label": cls.UNIT_LABELS[unit_type],
            "will_create_equipment": not bool(equipment),
            "will_create_component": selected_component is None,
            "equipment_id": int(selected_equipment.id) if selected_equipment and selected_equipment.id else None,
            "component_id": int(selected_component.id) if selected_component and selected_component.id else None,
            "component": cls._preview_component_merge(selected_component, payload),
            "equipment": cls._preview_equipment_merge(selected_equipment, payload),
        }

    @classmethod
    async def apply_to_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        unit_type: str,
        extracted: dict[str, Any],
        raw_text: str,
        validation_flags: dict[str, Any] | None,
        file_id: str,
        filename: str,
        mime_type: str | None,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        can_attach_any: bool = False,
    ) -> dict[str, Any] | None:
        if unit_type not in cls.UNIT_TYPES:
            raise ValueError("Неизвестный тип блока")
        allowed = await cls.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
        if not allowed:
            return None
        order = await cls._load_order(session, order_id)
        if not order:
            return None

        equipment = await cls._ensure_equipment_for_order(session, order)
        if not equipment:
            raise ValueError("Не удалось создать карточку оборудования для заказа")
        components = await cls._components_for_equipment(session, [int(item.id or 0) for item in equipment])
        payload = cls._component_payload_from_extracted(extracted)
        selected_equipment, selected_component = cls._select_equipment_component(
            equipment,
            components,
            unit_type=unit_type,
            payload=payload,
        )
        if not selected_equipment:
            raise ValueError("Не удалось выбрать карточку оборудования")

        equipment_merge = cls._preview_equipment_merge(selected_equipment, payload)
        for field, value in equipment_merge["applied"].items():
            setattr(selected_equipment, field, value)
        if selected_equipment.warranty_started_at is None:
            selected_equipment.warranty_started_at = EquipmentService._order_warranty_start(
                order,
                {"warranty_start_date": order.installation_date},
            )
        if selected_equipment.warranty_expires_at is None and selected_equipment.warranty_started_at:
            selected_equipment.warranty_expires_at = EquipmentService._add_months(
                selected_equipment.warranty_started_at,
                cls.WARRANTY_MONTHS_DEFAULT,
            )
        if selected_equipment.installed_at is None:
            selected_equipment.installed_at = EquipmentService._normalize_naive_datetime(order.installation_date)
        if selected_equipment.commissioned_at is None:
            selected_equipment.commissioned_at = selected_equipment.warranty_started_at
        selected_equipment.updated_at = datetime.now()
        session.add(selected_equipment)

        created_component = False
        if selected_component is None:
            selected_component = EquipmentComponent(
                equipment_id=int(selected_equipment.id or 0),
                catalog_product_id=selected_equipment.catalog_product_id,
                component_type=unit_type,
                title=cls.UNIT_LABELS[unit_type].capitalize(),
            )
            session.add(selected_component)
            await session.flush()
            created_component = True

        component_merge = cls._preview_component_merge(selected_component, payload)
        for field, value in component_merge["applied"].items():
            setattr(selected_component, field, value)
        selected_component.updated_at = datetime.now()
        session.add(selected_component)

        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        history = list(meta.get(cls.HISTORY_META_KEY)) if isinstance(meta.get(cls.HISTORY_META_KEY), list) else []
        attached_at = datetime.now()
        entry = BotOrderAttachmentService._build_entry(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            attached_at=attached_at,
        )
        entry.update(
            {
                "purpose": "warranty_nameplate",
                "unit_type": unit_type,
                "equipment_id": int(selected_equipment.id or 0),
                "component_id": int(selected_component.id or 0),
                "extracted": {key: value for key, value in payload.items() if value},
                "validation_flags": validation_flags or {},
                "component_applied_fields": list(component_merge["applied"].keys()),
                "component_conflicts": component_merge["conflicts"],
                "equipment_applied_fields": list(equipment_merge["applied"].keys()),
                "equipment_conflicts": equipment_merge["conflicts"],
                "raw_text": raw_text[:4000],
            }
        )
        history.append(entry)
        meta[cls.HISTORY_META_KEY] = history[-20:]
        order.technical_meta = meta
        flag_modified(order, "technical_meta")
        session.add(order)
        await session.commit()
        await session.refresh(selected_component)
        await session.refresh(selected_equipment)

        return {
            "id": int(order.id or 0),
            "equipment_id": int(selected_equipment.id or 0),
            "component_id": int(selected_component.id or 0),
            "unit_type": unit_type,
            "created_component": created_component,
            "component": component_merge,
            "equipment": equipment_merge,
            "extracted": payload,
        }
