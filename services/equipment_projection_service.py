"""Presentation helpers for the manager equipment registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from models import (
    CustomerEquipment,
    EquipmentComponent,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
)
from services.tenant_scope_service import TenantScope


class EquipmentProjectionService:
    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @classmethod
    def warranty_status(cls, equipment: CustomerEquipment) -> str:
        if equipment.warranty_mode == "none":
            return "none"
        now = datetime.now()
        starts_at = cls._naive(equipment.warranty_started_at)
        expires_at = cls._naive(equipment.warranty_expires_at)
        if expires_at is None:
            return "unknown"
        if starts_at and starts_at > now:
            return "scheduled"
        return "active" if expires_at >= now else "expired"

    @classmethod
    def to_equipment_item(cls, equipment: CustomerEquipment) -> dict[str, Any]:
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
            "warranty_mode": equipment.warranty_mode or "auto",
            "warranty_duration_months": equipment.warranty_duration_months,
            "warranty_started_at": equipment.warranty_started_at,
            "warranty_expires_at": equipment.warranty_expires_at,
            "warranty_terms": equipment.warranty_terms,
            "warranty_status": cls.warranty_status(equipment),
            "maintenance_enabled": bool(equipment.maintenance_enabled),
            "maintenance_interval_months": int(equipment.maintenance_interval_months or 12),
            "maintenance_anchor_at": equipment.maintenance_anchor_at,
            "notes": equipment.notes,
            "is_archived": bool(equipment.is_archived),
            "created_at": equipment.created_at,
            "updated_at": equipment.updated_at,
        }

    @staticmethod
    def to_history_item(entry: EquipmentServiceHistory) -> dict[str, Any]:
        event_type = entry.event_type.value if hasattr(entry.event_type, "value") else str(entry.event_type)
        return {
            "id": int(entry.id or 0),
            "equipment_id": int(entry.equipment_id),
            "order_id": entry.order_id,
            "event_type": event_type,
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
    def to_component_item(
        component: EquipmentComponent,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        return {
            "id": int(component.id or 0),
            "equipment_id": int(component.equipment_id),
            "catalog_product_id": component.catalog_product_id,
            "supplier_id": component.supplier_id if tenant_scope.is_system else None,
            "component_type": component.component_type,
            "title": component.title,
            "brand": component.brand,
            "model": component.model,
            "serial": component.serial,
            "inventory_number": component.inventory_number,
            "supplier_invoice_number": component.supplier_invoice_number if tenant_scope.is_system else None,
            "supplier_invoice_date": component.supplier_invoice_date if tenant_scope.is_system else None,
            "notes": component.notes,
            "is_archived": bool(component.is_archived),
            "created_at": component.created_at,
            "updated_at": component.updated_at,
        }

    @classmethod
    def apply_coverage_summary(
        cls,
        data: dict[str, Any],
        coverages: list[EquipmentWarrantyCoverage],
        *,
        now: datetime | None = None,
    ) -> None:
        if data.get("warranty_mode") == "none":
            data.update(
                warranty_status="none",
                warranty_started_at=None,
                warranty_expires_at=None,
                warranty_duration_months=None,
                warranty_terms=None,
            )
            return

        moment = cls._naive(now) or datetime.now()
        scoped = [
            item
            for item in coverages
            if item.component_id is None
            and item.decision_status != "voided"
            and item.coverage_type in {"supplier", "legacy"}
        ]
        if not scoped:
            data["warranty_status"] = "unknown"
            return

        def status(item: EquipmentWarrantyCoverage) -> str:
            starts_at = cls._naive(item.starts_at)
            expires_at = cls._naive(item.expires_at)
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
        starts = [cls._naive(item.starts_at) for item in scoped if item.starts_at is not None]
        expirations = [cls._naive(item.expires_at) for item in scoped if item.expires_at is not None]
        data["warranty_started_at"] = min((value for value in starts if value), default=None)
        data["warranty_expires_at"] = max((value for value in expirations if value), default=None)
        terms_item = next((item for item in scoped if item.terms_snapshot), None)
        data["warranty_terms"] = terms_item.terms_snapshot if terms_item else None
