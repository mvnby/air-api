"""Tenant-scoped warranty coverage reads and manager decisions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import EquipmentWarrantyCoverage, EquipmentWarrantyDecision
from models.tenancy import TenantScope
from services.tenant_entity_access_service import TenantEntityAccessService


class WarrantyCoverageService:
    DECISIONS = {"voided", "restored"}

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @classmethod
    def coverage_status(
        cls,
        coverage: EquipmentWarrantyCoverage,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        moment = cls._naive(now) or datetime.now()
        starts_at = cls._naive(coverage.starts_at)
        expires_at = cls._naive(coverage.expires_at)
        if coverage.decision_status == "voided":
            time_status = "voided"
        elif starts_at and starts_at > moment:
            time_status = "scheduled"
        elif expires_at is None:
            time_status = "unknown"
        else:
            time_status = "active" if expires_at >= moment else "expired"

        if not coverage.maintenance_required:
            maintenance_status = "not_required"
        elif coverage.next_maintenance_due_at is None:
            maintenance_status = "unknown"
        else:
            due_at = cls._naive(coverage.next_maintenance_due_at)
            grace_until = due_at + timedelta(days=int(coverage.grace_period_days or 0))
            if moment > grace_until:
                maintenance_status = "overdue"
            elif moment >= due_at - timedelta(days=30):
                maintenance_status = "due_soon"
            else:
                maintenance_status = "current"
        return {
            "time_status": time_status,
            "maintenance_status": maintenance_status,
            "requires_manager_decision": maintenance_status == "overdue"
            and coverage.decision_status == "none",
        }

    @classmethod
    def to_item(cls, coverage: EquipmentWarrantyCoverage) -> dict[str, Any]:
        return {
            "id": int(coverage.id or 0),
            "equipment_id": int(coverage.equipment_id),
            "component_id": coverage.component_id,
            "policy_id": coverage.policy_id,
            "coverage_type": coverage.coverage_type,
            "source": coverage.source,
            "starts_at": coverage.starts_at,
            "expires_at": coverage.expires_at,
            "maintenance_required": bool(coverage.maintenance_required),
            "maintenance_interval_months": coverage.maintenance_interval_months,
            "grace_period_days": int(coverage.grace_period_days or 0),
            "allowed_maintenance_provider": coverage.allowed_maintenance_provider,
            "next_maintenance_due_at": coverage.next_maintenance_due_at,
            "terms_snapshot": coverage.terms_snapshot,
            "policy_snapshot": coverage.policy_snapshot,
            "decision_status": coverage.decision_status,
            "decision_reason": coverage.decision_reason,
            "decided_at": coverage.decided_at,
            "decided_by": coverage.decided_by,
            **cls.coverage_status(coverage),
            "created_at": coverage.created_at,
            "updated_at": coverage.updated_at,
        }

    @classmethod
    async def list_coverages(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]] | None:
        equipment = await TenantEntityAccessService.get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if equipment is None:
            return None
        result = await session.execute(
            select(EquipmentWarrantyCoverage)
            .where(EquipmentWarrantyCoverage.equipment_id == equipment_id)
            .order_by(
                EquipmentWarrantyCoverage.coverage_type,
                EquipmentWarrantyCoverage.id,
            )
        )
        return [cls.to_item(item) for item in result.scalars().all()]

    @classmethod
    async def record_decision(
        cls,
        session: AsyncSession,
        *,
        coverage_id: int,
        action: str,
        reason: str,
        decided_by: str,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        coverage = await TenantEntityAccessService.get_warranty_coverage(
            session,
            coverage_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if coverage is None:
            return None
        return await cls._record_decision(
            session,
            coverage=coverage,
            action=action,
            reason=reason,
            decided_by=decided_by,
        )

    @classmethod
    async def _record_decision(
        cls,
        session: AsyncSession,
        *,
        coverage: EquipmentWarrantyCoverage,
        action: str,
        reason: str,
        decided_by: str,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in cls.DECISIONS:
            raise ValueError("Warranty decision must be voided or restored")
        cleaned_reason = " ".join(str(reason or "").split())
        if not cleaned_reason:
            raise ValueError("Warranty decision reason is required")

        coverage.decision_status = normalized_action
        coverage.decision_reason = cleaned_reason
        coverage.decided_at = datetime.now()
        coverage.decided_by = decided_by
        coverage.updated_at = datetime.now()
        session.add(coverage)
        session.add(
            EquipmentWarrantyDecision(
                coverage_id=int(coverage.id or 0),
                action=normalized_action,
                reason=cleaned_reason,
                decided_by=decided_by,
            )
        )
        if normalized_action == "restored":
            from services.warranty_maintenance_service import WarrantyMaintenanceService

            await session.flush()
            await WarrantyMaintenanceService.restore_from_latest_maintenance(
                session,
                coverage=coverage,
            )
        await session.commit()
        await session.refresh(coverage)
        return cls.to_item(coverage)
