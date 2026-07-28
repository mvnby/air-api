from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerEquipment,
    EquipmentComponent,
    EquipmentOrderLink,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    Order,
    OrderProductLink,
    Product,
    Supplier,
)
from services.tenant_scope_service import TenantScope


class EquipmentService:
    TRUE_VALUES = {"1", "true", "yes", "y", "да", "д", "истина"}
    FALSE_VALUES = {"0", "false", "no", "n", "нет", "н", "ложь"}
    REPAIR_HISTORY_AUTO_SYNC_STATUSES = frozenset({"completed", "not_repairable"})
    EQUIPMENT_SOURCES = frozenset({"sold_by_us", "installed_by_us", "customer_owned", "unknown"})
    COMPONENT_TYPES = frozenset({"system", "indoor_unit", "outdoor_unit", "remote", "wifi_module", "other"})
    ORDER_LINK_ROLES = frozenset({"sale", "installation", "maintenance", "repair", "diagnostic", "warranty_case", "other"})
    MAINTENANCE_PROVIDERS = frozenset({"mvn", "authorized", "external"})

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
    def _add_months(dt: datetime, months: int) -> datetime:
        month = dt.month - 1 + max(0, int(months))
        year = dt.year + month // 12
        month = month % 12 + 1
        month_days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        day = min(dt.day, month_days[month - 1])
        return dt.replace(year=year, month=month, day=day)

    @staticmethod
    def _normalize_equipment_source(raw: Any) -> str:
        value = EquipmentService._clean_optional_text(raw) or "unknown"
        if value not in EquipmentService.EQUIPMENT_SOURCES:
            allowed = ", ".join(sorted(EquipmentService.EQUIPMENT_SOURCES))
            raise ValueError(f"Invalid equipment_source: {raw}. Allowed: {allowed}")
        return value

    @staticmethod
    def _normalize_component_type(raw: Any) -> str:
        value = EquipmentService._clean_optional_text(raw) or "other"
        if value not in EquipmentService.COMPONENT_TYPES:
            allowed = ", ".join(sorted(EquipmentService.COMPONENT_TYPES))
            raise ValueError(f"Invalid component_type: {raw}. Allowed: {allowed}")
        return value

    @staticmethod
    def _normalize_order_link_role(raw: Any) -> str:
        value = EquipmentService._clean_optional_text(raw) or "other"
        if value not in EquipmentService.ORDER_LINK_ROLES:
            allowed = ", ".join(sorted(EquipmentService.ORDER_LINK_ROLES))
            raise ValueError(f"Invalid equipment order role: {raw}. Allowed: {allowed}")
        return value

    @staticmethod
    def _normalize_maintenance_provider(raw: Any) -> Optional[str]:
        value = EquipmentService._clean_optional_text(raw)
        if value is None:
            return None
        if value not in EquipmentService.MAINTENANCE_PROVIDERS:
            allowed = ", ".join(sorted(EquipmentService.MAINTENANCE_PROVIDERS))
            raise ValueError(f"Invalid maintenance provider: {raw}. Allowed: {allowed}")
        return value

    @staticmethod
    async def _ensure_equipment_order_link(
        session: AsyncSession,
        *,
        equipment_id: int,
        order_id: int,
        role: str,
    ) -> EquipmentOrderLink:
        normalized_role = EquipmentService._normalize_order_link_role(role)
        result = await session.execute(
            select(EquipmentOrderLink).where(
                EquipmentOrderLink.equipment_id == equipment_id,
                EquipmentOrderLink.order_id == order_id,
                EquipmentOrderLink.role == normalized_role,
            )
        )
        link = result.scalars().first()
        if link:
            return link
        link = EquipmentOrderLink(equipment_id=equipment_id, order_id=order_id, role=normalized_role)
        session.add(link)
        await session.flush()
        return link

    @staticmethod
    def _warranty_status(equipment: CustomerEquipment) -> str:
        now = datetime.now()
        starts_at = EquipmentService._normalize_naive_datetime(equipment.warranty_started_at)
        expires_at = EquipmentService._normalize_naive_datetime(equipment.warranty_expires_at)
        if expires_at is None:
            return "unknown" if starts_at else "none"
        if starts_at and starts_at > now:
            return "scheduled"
        return "active" if expires_at >= now else "expired"

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
    def _product_brand_title(product: Optional[Product]) -> Optional[str]:
        brand = getattr(product, "brand", None) if product else None
        return EquipmentService._clean_optional_text(getattr(brand, "title", None))

    @staticmethod
    def _product_spec_text(product: Optional[Product], *keys: str) -> Optional[str]:
        specs = getattr(product, "specs", None) if product else None
        if not isinstance(specs, dict):
            return None
        normalized = {str(key).strip().casefold(): value for key, value in specs.items()}
        for key in keys:
            value = normalized.get(key.strip().casefold())
            cleaned = EquipmentService._clean_optional_text(value)
            if cleaned:
                return cleaned
        return None

    @staticmethod
    def _selected_order_product_links(order: Order) -> list[OrderProductLink]:
        selected_proposal = next(
            (proposal for proposal in getattr(order, "proposals", []) if proposal.is_selected and not proposal.is_archived),
            None,
        )
        if not selected_proposal:
            selected_proposal = next(
                (proposal for proposal in sorted(getattr(order, "proposals", []), key=lambda item: item.sort_order) if not proposal.is_archived),
                None,
            )
        selected_proposal_id = selected_proposal.id if selected_proposal and selected_proposal.id is not None else None
        return [
            link
            for link in getattr(order, "product_links", [])
            if selected_proposal_id is None or link.proposal_id == selected_proposal_id
        ]

    @staticmethod
    def _order_warranty_start(order: Order, payload: Dict[str, Any]) -> Optional[datetime]:
        return EquipmentService._normalize_naive_datetime(payload.get("warranty_start_date"))

    @staticmethod
    def _to_equipment_item(equipment: CustomerEquipment) -> Dict[str, Any]:
        return {
            "id": int(equipment.id or 0),
            "customer_id": int(equipment.customer_id),
            "customer_branch_id": equipment.customer_branch_id,
            "catalog_product_id": equipment.catalog_product_id,
            "source_order_id": equipment.source_order_id,
            "equipment_type": equipment.equipment_type,
            "equipment_source": equipment.equipment_source or "unknown",
            "display_name": equipment.display_name,
            "brand": equipment.brand,
            "model": equipment.model,
            "serial": equipment.serial,
            "inventory_number": equipment.inventory_number,
            "location_hint": equipment.location_hint,
            "refrigerant_type": equipment.refrigerant_type,
            "installed_at": equipment.installed_at,
            "commissioned_at": equipment.commissioned_at,
            "warranty_started_at": equipment.warranty_started_at,
            "warranty_expires_at": equipment.warranty_expires_at,
            "warranty_terms": equipment.warranty_terms,
            "warranty_status": EquipmentService._warranty_status(equipment),
            "notes": equipment.notes,
            "is_archived": bool(equipment.is_archived),
            "created_at": equipment.created_at,
            "updated_at": equipment.updated_at,
        }

    @staticmethod
    def _apply_coverage_summary(
        data: Dict[str, Any],
        coverages: list[EquipmentWarrantyCoverage],
        *,
        now: datetime | None = None,
    ) -> None:
        """Keep compact registry fields aligned with immutable warranty coverages."""

        moment = EquipmentService._normalize_naive_datetime(now) or datetime.now()
        available = [item for item in coverages if item.decision_status != "voided"]
        if not available:
            return
        primary = [item for item in available if item.coverage_type in {"supplier", "legacy"}]
        scoped = primary or available

        def status(item: EquipmentWarrantyCoverage) -> str:
            starts_at = EquipmentService._normalize_naive_datetime(item.starts_at)
            expires_at = EquipmentService._normalize_naive_datetime(item.expires_at)
            if starts_at and starts_at > moment:
                return "scheduled"
            if expires_at is None:
                return "unknown"
            return "active" if expires_at >= moment else "expired"

        statuses = {status(item) for item in scoped}
        for candidate in ("active", "scheduled", "unknown", "expired"):
            if candidate in statuses:
                data["warranty_status"] = candidate
                break
        starts = [
            EquipmentService._normalize_naive_datetime(item.starts_at)
            for item in scoped
            if item.starts_at is not None
        ]
        expirations = [
            EquipmentService._normalize_naive_datetime(item.expires_at)
            for item in scoped
            if item.expires_at is not None
        ]
        data["warranty_started_at"] = min((value for value in starts if value), default=None)
        data["warranty_expires_at"] = max((value for value in expirations if value), default=None)
        terms_item = next((item for item in scoped if item.terms_snapshot), None)
        data["warranty_terms"] = terms_item.terms_snapshot if terms_item else None

    @staticmethod
    def _to_history_item(entry: EquipmentServiceHistory) -> Dict[str, Any]:
        return {
            "id": int(entry.id or 0),
            "equipment_id": int(entry.equipment_id),
            "order_id": entry.order_id,
            "event_type": EquipmentService._enum_value(entry.event_type),
            "event_date": entry.event_date,
            "maintenance_provider": entry.maintenance_provider,
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
    def _to_component_item(component: EquipmentComponent) -> Dict[str, Any]:
        return {
            "id": int(component.id or 0),
            "equipment_id": int(component.equipment_id),
            "catalog_product_id": component.catalog_product_id,
            "supplier_id": component.supplier_id,
            "component_type": component.component_type,
            "title": component.title,
            "brand": component.brand,
            "model": component.model,
            "serial": component.serial,
            "inventory_number": component.inventory_number,
            "supplier_invoice_number": component.supplier_invoice_number,
            "supplier_invoice_date": component.supplier_invoice_date,
            "notes": component.notes,
            "is_archived": bool(component.is_archived),
            "created_at": component.created_at,
            "updated_at": component.updated_at,
        }

    @staticmethod
    def _component_values_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "component_type": EquipmentService._normalize_component_type(payload.get("component_type")),
            "title": EquipmentService._clean_optional_text(payload.get("title")),
            "brand": EquipmentService._clean_optional_text(payload.get("brand")),
            "model": EquipmentService._clean_optional_text(payload.get("model")),
            "serial": EquipmentService._clean_optional_text(payload.get("serial")),
            "inventory_number": EquipmentService._clean_optional_text(payload.get("inventory_number")),
            "supplier_invoice_number": EquipmentService._clean_optional_text(payload.get("supplier_invoice_number")),
            "supplier_invoice_date": EquipmentService._normalize_naive_datetime(payload.get("supplier_invoice_date")),
            "notes": EquipmentService._clean_optional_text(payload.get("notes")),
        }

    @staticmethod
    def _history_values_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        order_id = payload.get("order_id")
        event_type = EquipmentService._normalize_event_type(payload.get("event_type"))
        maintenance_provider = EquipmentService._normalize_maintenance_provider(payload.get("maintenance_provider"))
        if event_type == EquipmentServiceEventType.MAINTENANCE and maintenance_provider is None:
            maintenance_provider = "mvn" if order_id is not None else None
            if maintenance_provider is None:
                raise ValueError("Maintenance provider is required for a maintenance event")
        return {
            "order_id": int(order_id) if order_id is not None else None,
            "event_type": event_type,
            "event_date": EquipmentService._normalize_naive_datetime(payload.get("event_date")) or datetime.now(),
            "maintenance_provider": maintenance_provider if event_type == EquipmentServiceEventType.MAINTENANCE else None,
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
    async def _ensure_product_exists(session: AsyncSession, product_id: int) -> Product:
        product = await session.get(Product, product_id)
        if not product:
            raise ValueError("Catalog product not found")
        return product

    @staticmethod
    async def _ensure_supplier_exists(session: AsyncSession, supplier_id: int) -> Supplier:
        supplier = await session.get(Supplier, supplier_id)
        if not supplier:
            raise ValueError("Supplier not found")
        return supplier

    @staticmethod
    async def _ensure_source_order_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        source_order_id: int,
    ) -> Order:
        order = await session.get(Order, source_order_id)
        if not order:
            raise ValueError("Source order not found")
        if order.customer_id is None:
            raise ValueError("Source order customer is required")
        if int(order.customer_id) != int(customer_id):
            raise ValueError("Source order customer does not match equipment customer")
        return order

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
    async def _get_equipment_component(
        session: AsyncSession,
        *,
        equipment_id: int,
        component_id: int,
    ) -> Optional[EquipmentComponent]:
        result = await session.execute(
            select(EquipmentComponent).where(
                EquipmentComponent.id == component_id,
                EquipmentComponent.equipment_id == equipment_id,
            )
        )
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
        q: str | None = None,
        attention: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_registry_service import EquipmentRegistryService
        return await EquipmentRegistryService.list_equipment(
            session, customer_id=customer_id, customer_branch_id=customer_branch_id,
            page=page, limit=limit, include_archived=include_archived, q=q, attention=attention,
        )

    @staticmethod
    async def get_equipment_detail(
        session: AsyncSession, *, equipment_id: int, history_limit: int,
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_registry_service import EquipmentRegistryService
        return await EquipmentRegistryService.get_equipment_detail(
            session, equipment_id=equipment_id, history_limit=history_limit,
        )

    @staticmethod
    async def create_equipment(
        session: AsyncSession, *, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_workflow_service import EquipmentWorkflowService
        return await EquipmentWorkflowService.create_equipment(session, payload=payload)

    @staticmethod
    async def update_equipment(
        session: AsyncSession, *, equipment_id: int, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_workflow_service import EquipmentWorkflowService
        return await EquipmentWorkflowService.update_equipment(
            session, equipment_id=equipment_id, payload=payload,
        )

    @staticmethod
    async def create_equipment_from_order(
        session: AsyncSession, *, order_id: int, payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        from services.equipment_workflow_service import EquipmentWorkflowService
        return await EquipmentWorkflowService.create_equipment_from_order(
            session, order_id=order_id, payload=payload,
        )

    @staticmethod
    async def create_maintenance_order(
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_workflow_service import EquipmentWorkflowService
        return await EquipmentWorkflowService.create_maintenance_order(
            session,
            equipment_id=equipment_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_components(
        session: AsyncSession, *, equipment_id: int, include_archived: bool = False,
    ) -> list[Dict[str, Any]]:
        from services.equipment_component_service import EquipmentComponentService
        return await EquipmentComponentService.list_components(
            session, equipment_id=equipment_id, include_archived=include_archived,
        )

    @staticmethod
    async def create_component(
        session: AsyncSession, *, equipment_id: int, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_component_service import EquipmentComponentService
        return await EquipmentComponentService.create_component(
            session, equipment_id=equipment_id, payload=payload,
        )

    @staticmethod
    async def update_component(
        session: AsyncSession, *, equipment_id: int, component_id: int, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_component_service import EquipmentComponentService
        return await EquipmentComponentService.update_component(
            session, equipment_id=equipment_id, component_id=component_id, payload=payload,
        )

    @staticmethod
    async def list_history(
        session: AsyncSession, *, equipment_id: int, page: int, limit: int,
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_history_service import EquipmentHistoryService
        return await EquipmentHistoryService.list_history(
            session, equipment_id=equipment_id, page=page, limit=limit,
        )

    @staticmethod
    async def _lock_order_for_history_sync(
        session: AsyncSession, *, order_id: int,
    ) -> None:
        from services.equipment_history_service import EquipmentHistoryService
        await EquipmentHistoryService._lock_order_for_history_sync(session, order_id=order_id)

    @staticmethod
    async def _list_history_for_order(
        session: AsyncSession, *, order_id: int,
    ) -> list[EquipmentServiceHistory]:
        from services.equipment_history_service import EquipmentHistoryService
        return await EquipmentHistoryService._list_history_for_order(session, order_id=order_id)

    @staticmethod
    async def add_history(
        session: AsyncSession, *, equipment_id: int, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_history_service import EquipmentHistoryService
        return await EquipmentHistoryService.add_history(
            session, equipment_id=equipment_id, payload=payload,
        )

    @staticmethod
    def _infer_repair_history_event_type(repair_meta: Dict[str, Any]) -> EquipmentServiceEventType:
        from services.equipment_history_service import EquipmentHistoryService
        return EquipmentHistoryService._infer_repair_history_event_type(repair_meta)

    @staticmethod
    def build_history_payload_from_repair_order(
        order: Order, *, event_type: Optional[Any] = None,
        event_date: Optional[datetime] = None, notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        from services.equipment_history_service import EquipmentHistoryService
        return EquipmentHistoryService.build_history_payload_from_repair_order(
            order, event_type=event_type, event_date=event_date, notes=notes,
        )

    @staticmethod
    async def add_history_from_repair_order(
        session: AsyncSession, *, equipment_id: int, payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from services.equipment_history_service import EquipmentHistoryService
        return await EquipmentHistoryService.add_history_from_repair_order(
            session, equipment_id=equipment_id, payload=payload,
        )
