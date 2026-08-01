"""Warranty policy resolution and immutable equipment coverage snapshots."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Brand,
    CustomerEquipment,
    EquipmentServiceEventType,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
    Product,
    ProductSeries,
    Supplier,
    WarrantyPolicy,
)
from models.tenancy import TenantScope
from services.tenant_entity_access_service import TenantEntityAccessService


class WarrantyService:
    COVERAGE_TYPES = {"supplier", "mvn_work", "legacy"}
    DECISIONS = {"voided", "restored"}

    @staticmethod
    def policy_to_item(
        policy: WarrantyPolicy,
        *,
        scope_names: dict[str, dict[int, Any]] | None = None,
    ) -> dict[str, Any]:
        names = scope_names or {}
        return {
            "id": int(policy.id or 0),
            "name": policy.name,
            "coverage_type": policy.coverage_type,
            "supplier_id": policy.supplier_id,
            "brand_id": policy.brand_id,
            "series_id": policy.series_id,
            "product_id": policy.product_id,
            "supplier_name": names.get("suppliers", {}).get(int(policy.supplier_id or 0)),
            "brand_title": names.get("brands", {}).get(int(policy.brand_id or 0)),
            "series_title": names.get("series", {}).get(int(policy.series_id or 0)),
            "series_brand_id": names.get("series_brand_ids", {}).get(int(policy.series_id or 0)),
            "product_title": names.get("products", {}).get(int(policy.product_id or 0)),
            "duration_months": policy.duration_months,
            "start_event": policy.start_event,
            "maintenance_required": bool(policy.maintenance_required),
            "maintenance_interval_months": policy.maintenance_interval_months,
            "grace_period_days": int(policy.grace_period_days or 0),
            "allowed_maintenance_provider": policy.allowed_maintenance_provider,
            "terms": policy.terms,
            "effective_from": policy.effective_from,
            "effective_until": policy.effective_until,
            "is_active": bool(policy.is_active),
            "created_at": policy.created_at,
            "updated_at": policy.updated_at,
        }

    @staticmethod
    async def _policy_scope_names(
        session: AsyncSession,
        policies: list[WarrantyPolicy],
    ) -> dict[str, dict[int, Any]]:
        lookups: tuple[tuple[str, Any, Any, set[int]], ...] = (
            ("suppliers", Supplier, Supplier.name, {int(item.supplier_id) for item in policies if item.supplier_id}),
            ("brands", Brand, Brand.title, {int(item.brand_id) for item in policies if item.brand_id}),
            ("products", Product, Product.title, {int(item.product_id) for item in policies if item.product_id}),
        )
        names: dict[str, dict[int, Any]] = {}
        for key, model, title_field, ids in lookups:
            if not ids:
                names[key] = {}
                continue
            result = await session.execute(select(model.id, title_field).where(model.id.in_(ids)))
            names[key] = {int(item_id): str(title) for item_id, title in result.all()}
        series_ids = {int(item.series_id) for item in policies if item.series_id}
        names["series"] = {}
        names["series_brand_ids"] = {}
        if series_ids:
            result = await session.execute(
                select(ProductSeries.id, ProductSeries.title, ProductSeries.brand_id).where(
                    ProductSeries.id.in_(series_ids)
                )
            )
            for series_id, title, brand_id in result.all():
                names["series"][int(series_id)] = str(title)
                names["series_brand_ids"][int(series_id)] = int(brand_id)
        return names

    @classmethod
    def _validated_policy_values(cls, payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
        values = dict(payload)
        if "name" in values:
            values["name"] = " ".join(str(values.get("name") or "").split())
            if not values["name"]:
                raise ValueError("Warranty policy name is required")
        elif not partial:
            raise ValueError("Warranty policy name is required")
        if "coverage_type" in values:
            coverage_type = str(values.get("coverage_type") or "").strip()
            if coverage_type not in {"supplier", "mvn_work"}:
                raise ValueError("Unsupported warranty coverage type")
            values["coverage_type"] = coverage_type
        if "duration_months" in values and values["duration_months"] is not None:
            values["duration_months"] = int(values["duration_months"])
            if not 0 < values["duration_months"] <= 240:
                raise ValueError("Warranty duration must be between 1 and 240 months")
        if "maintenance_interval_months" in values and values["maintenance_interval_months"] is not None:
            values["maintenance_interval_months"] = int(values["maintenance_interval_months"])
            if not 0 < values["maintenance_interval_months"] <= 60:
                raise ValueError("Maintenance interval must be between 1 and 60 months")
        if values.get("maintenance_required") is True and not values.get("maintenance_interval_months") and not partial:
            raise ValueError("Maintenance interval is required when maintenance is mandatory")
        if "grace_period_days" in values:
            values["grace_period_days"] = int(values.get("grace_period_days") or 0)
            if not 0 <= values["grace_period_days"] <= 365:
                raise ValueError("Warranty grace period must be between 0 and 365 days")
        if "start_event" in values and values["start_event"] not in {"sale", "installation", "commissioning", "manual"}:
            raise ValueError("Unsupported warranty start event")
        if "allowed_maintenance_provider" in values and values["allowed_maintenance_provider"] not in {
            "any",
            "mvn",
            "authorized",
        }:
            raise ValueError("Unsupported maintenance provider rule")
        return values

    @classmethod
    async def list_policies(
        cls,
        session: AsyncSession,
        *,
        supplier_id: int | None = None,
        brand_id: int | None = None,
        series_id: int | None = None,
        product_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        filters = []
        if supplier_id is not None:
            filters.append(WarrantyPolicy.supplier_id == supplier_id)
        if brand_id is not None:
            filters.append(WarrantyPolicy.brand_id == brand_id)
        if series_id is not None:
            filters.append(WarrantyPolicy.series_id == series_id)
        if product_id is not None:
            filters.append(WarrantyPolicy.product_id == product_id)
        if not include_inactive:
            filters.append(WarrantyPolicy.is_active == True)
        result = await session.execute(
            select(WarrantyPolicy)
            .where(*filters)
            .order_by(WarrantyPolicy.is_active.desc(), WarrantyPolicy.name, WarrantyPolicy.id)
        )
        policies = list(result.scalars().all())
        scope_names = await cls._policy_scope_names(session, policies)
        return [cls.policy_to_item(item, scope_names=scope_names) for item in policies]

    @classmethod
    async def create_policy(cls, session: AsyncSession, *, payload: dict[str, Any]) -> dict[str, Any]:
        values = cls._validated_policy_values(payload, partial=False)
        if not any(values.get(key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(session, values)
        policy = WarrantyPolicy(**values)
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        scope_names = await cls._policy_scope_names(session, [policy])
        return cls.policy_to_item(policy, scope_names=scope_names)

    @classmethod
    async def update_policy(
        cls,
        session: AsyncSession,
        *,
        policy_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        policy = await session.get(WarrantyPolicy, policy_id)
        if not policy:
            return None
        values = cls._validated_policy_values(payload, partial=True)
        for field, value in values.items():
            setattr(policy, field, value)
        if policy.maintenance_required and not policy.maintenance_interval_months:
            raise ValueError("Maintenance interval is required when maintenance is mandatory")
        if not any(getattr(policy, key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(
            session,
            {
                "supplier_id": policy.supplier_id,
                "brand_id": policy.brand_id,
                "series_id": policy.series_id,
                "product_id": policy.product_id,
            },
        )
        policy.updated_at = datetime.now()
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        scope_names = await cls._policy_scope_names(session, [policy])
        return cls.policy_to_item(policy, scope_names=scope_names)

    @staticmethod
    async def _validate_policy_scope(session: AsyncSession, values: dict[str, Any]) -> None:
        supplier_id = values.get("supplier_id")
        brand_id = values.get("brand_id")
        series_id = values.get("series_id")
        product_id = values.get("product_id")
        if supplier_id is not None and not await session.get(Supplier, int(supplier_id)):
            raise ValueError("Warranty policy supplier not found")
        brand = await session.get(Brand, int(brand_id)) if brand_id is not None else None
        if brand_id is not None and not brand:
            raise ValueError("Warranty policy brand not found")
        series = await session.get(ProductSeries, int(series_id)) if series_id is not None else None
        if series_id is not None and not series:
            raise ValueError("Warranty policy series not found")
        product = await session.get(Product, int(product_id)) if product_id is not None else None
        if product_id is not None and not product:
            raise ValueError("Warranty policy product not found")
        if series and brand_id is not None and int(series.brand_id) != int(brand_id):
            raise ValueError("Warranty policy series does not belong to the selected brand")
        if product and brand_id is not None and int(product.brand_id or 0) != int(brand_id):
            raise ValueError("Warranty policy product does not belong to the selected brand")
        if product and series_id is not None and int(product.series_id or 0) != int(series_id):
            raise ValueError("Warranty policy product does not belong to the selected series")

    @staticmethod
    async def _existing_system_coverage(
        session: AsyncSession,
        *,
        equipment_id: int,
        coverage_type: str,
    ) -> EquipmentWarrantyCoverage | None:
        result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == equipment_id,
                EquipmentWarrantyCoverage.component_id.is_(None),
                EquipmentWarrantyCoverage.coverage_type == coverage_type,
            )
        )
        return result.scalars().first()

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        from services.equipment_service import EquipmentService

        return EquipmentService._add_months(value, months)

    @staticmethod
    def _warranty_months_from_product(product: Product | None) -> int | None:
        specs = getattr(product, "specs", None) if product else None
        if not isinstance(specs, dict):
            return None
        raw: Any = specs.get("warranty_months")
        if isinstance(raw, dict):
            raw = raw.get("value") or raw.get("normalized") or raw.get("raw")
        if isinstance(raw, (int, float)):
            value = int(raw)
            return value if value > 0 else None
        match = re.search(r"\d+", str(raw or ""))
        if not match:
            return None
        value = int(match.group())
        return value if 0 < value <= 240 else None

    @staticmethod
    def _policy_matches(
        policy: WarrantyPolicy,
        *,
        product: Product | None,
        supplier_id: int | None,
    ) -> bool:
        if policy.supplier_id is not None and int(policy.supplier_id) != int(supplier_id or 0):
            return False
        if policy.product_id is not None and (not product or int(policy.product_id) != int(product.id or 0)):
            return False
        if policy.series_id is not None and (not product or int(policy.series_id) != int(product.series_id or 0)):
            return False
        if policy.brand_id is not None and (not product or int(policy.brand_id) != int(product.brand_id or 0)):
            return False
        return True

    @staticmethod
    def _policy_score(policy: WarrantyPolicy) -> tuple[int, int]:
        if policy.product_id is not None:
            scope_specificity = 4
        elif policy.series_id is not None:
            scope_specificity = 3
        elif policy.brand_id is not None:
            scope_specificity = 2
        else:
            scope_specificity = 1
        return scope_specificity, int(policy.supplier_id is not None)

    @classmethod
    async def resolve_policy(
        cls,
        session: AsyncSession,
        *,
        product: Product | None,
        supplier_id: int | None,
        coverage_type: str = "supplier",
        at: datetime | None = None,
    ) -> WarrantyPolicy | None:
        moment = cls._naive(at) or datetime.now()
        result = await session.execute(
            select(WarrantyPolicy).where(
                WarrantyPolicy.is_active == True,
                WarrantyPolicy.coverage_type == coverage_type,
            )
        )
        candidates = []
        for policy in result.scalars().all():
            if policy.effective_from and cls._naive(policy.effective_from) > moment:
                continue
            if policy.effective_until and cls._naive(policy.effective_until) < moment:
                continue
            if cls._policy_matches(policy, product=product, supplier_id=supplier_id):
                candidates.append(policy)
        candidates.sort(key=lambda item: (cls._policy_score(item), item.created_at, item.id or 0), reverse=True)
        return candidates[0] if candidates else None

    @staticmethod
    def _start_for_event(
        *,
        event: str,
        equipment: CustomerEquipment,
        explicit: datetime | None,
        sale_at: datetime | None = None,
    ) -> datetime | None:
        if explicit:
            return WarrantyService._naive(explicit)
        if event == "installation":
            return WarrantyService._naive(equipment.installed_at)
        if event == "sale":
            return WarrantyService._naive(sale_at or equipment.commissioned_at or equipment.installed_at)
        if event == "manual":
            return None
        return WarrantyService._naive(equipment.commissioned_at or equipment.installed_at)

    @classmethod
    async def create_supplier_coverage(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        product: Product | None,
        supplier_id: int | None,
        explicit_start: datetime | None = None,
        sale_at: datetime | None = None,
        manual_expires_at: datetime | None = None,
        manual_terms: str | None = None,
    ) -> EquipmentWarrantyCoverage | None:
        existing = await cls._existing_system_coverage(
            session,
            equipment_id=int(equipment.id or 0),
            coverage_type="supplier",
        )
        if existing:
            return existing
        policy_at = explicit_start or sale_at or equipment.commissioned_at or equipment.installed_at
        policy = None
        if manual_expires_at is None:
            policy = await cls.resolve_policy(
                session,
                product=product,
                supplier_id=supplier_id,
                coverage_type="supplier",
                at=policy_at,
            )
        if manual_expires_at is not None:
            duration_months = None
            start_event = "manual"
            maintenance_required = False
            interval = None
            grace = 0
            provider = "any"
            terms = manual_terms
            source = "manual"
            snapshot = {
                "starts_at": cls._naive(explicit_start).isoformat() if explicit_start else None,
                "expires_at": cls._naive(manual_expires_at).isoformat(),
                "terms": manual_terms,
            }
        elif policy:
            duration_months = policy.duration_months
            start_event = policy.start_event
            maintenance_required = bool(policy.maintenance_required)
            interval = policy.maintenance_interval_months
            grace = int(policy.grace_period_days or 0)
            provider = policy.allowed_maintenance_provider or "any"
            terms = policy.terms
            source = "policy"
            snapshot = {
                "policy_id": policy.id,
                "policy_name": policy.name,
                "supplier_id": policy.supplier_id,
                "brand_id": policy.brand_id,
                "series_id": policy.series_id,
                "product_id": policy.product_id,
                "duration_months": policy.duration_months,
                "start_event": policy.start_event,
                "maintenance_required": policy.maintenance_required,
                "maintenance_interval_months": policy.maintenance_interval_months,
                "grace_period_days": policy.grace_period_days,
                "allowed_maintenance_provider": policy.allowed_maintenance_provider,
                "terms": policy.terms,
            }
        else:
            duration_months = cls._warranty_months_from_product(product)
            if duration_months is None:
                return None
            start_event = "commissioning"
            maintenance_required = False
            interval = None
            grace = 0
            provider = "any"
            terms = None
            source = "product_spec"
            snapshot = {
                "duration_months": duration_months,
                "source_spec": "warranty_months",
                "product_id": int(product.id or 0) if product else None,
            }

        starts_at = cls._start_for_event(
            event=start_event,
            equipment=equipment,
            explicit=explicit_start,
            sale_at=sale_at,
        )
        expires_at = cls._naive(manual_expires_at)
        if expires_at is None and starts_at and duration_months:
            expires_at = cls._add_months(starts_at, duration_months)
        next_due = cls._add_months(starts_at, interval) if starts_at and maintenance_required and interval else None
        coverage = EquipmentWarrantyCoverage(
            equipment_id=int(equipment.id or 0),
            policy_id=policy.id if policy else None,
            coverage_type="supplier",
            source=source,
            starts_at=starts_at,
            expires_at=expires_at,
            maintenance_required=maintenance_required,
            maintenance_interval_months=interval,
            grace_period_days=grace,
            allowed_maintenance_provider=provider,
            next_maintenance_due_at=next_due,
            terms_snapshot=terms,
            policy_snapshot=snapshot,
        )
        session.add(coverage)
        await session.flush()
        return coverage

    @classmethod
    async def create_work_coverage(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        duration_months: int | None,
        starts_at: datetime | None,
        terms: str | None = None,
        product: Product | None = None,
        supplier_id: int | None = None,
        sale_at: datetime | None = None,
    ) -> EquipmentWarrantyCoverage | None:
        existing = await cls._existing_system_coverage(
            session,
            equipment_id=int(equipment.id or 0),
            coverage_type="mvn_work",
        )
        if existing:
            return existing
        explicit_duration = duration_months is not None
        policy_at = starts_at or sale_at or equipment.installed_at or equipment.commissioned_at
        policy = await cls.resolve_policy(
            session,
            product=product,
            supplier_id=supplier_id,
            coverage_type="mvn_work",
            at=policy_at,
        )
        duration_months = duration_months if explicit_duration else (policy.duration_months if policy else None)
        if terms is None and policy:
            terms = policy.terms
        if duration_months is None or int(duration_months) <= 0:
            return None
        maintenance_required = bool(policy.maintenance_required) if policy else False
        interval = policy.maintenance_interval_months if policy else None
        grace = int(policy.grace_period_days or 0) if policy else 0
        provider = policy.allowed_maintenance_provider if policy else "any"
        start = cls._start_for_event(
            event=policy.start_event if policy else "installation",
            equipment=equipment,
            explicit=starts_at if explicit_duration else None,
            sale_at=sale_at,
        )
        next_due = cls._add_months(start, interval) if start and maintenance_required and interval else None
        coverage = EquipmentWarrantyCoverage(
            equipment_id=int(equipment.id or 0),
            policy_id=policy.id if policy else None,
            coverage_type="mvn_work",
            source="policy_override" if policy and explicit_duration else ("policy" if policy else "manual"),
            starts_at=start,
            expires_at=cls._add_months(start, int(duration_months)) if start else None,
            maintenance_required=maintenance_required,
            maintenance_interval_months=interval,
            grace_period_days=grace,
            allowed_maintenance_provider=provider,
            next_maintenance_due_at=next_due,
            terms_snapshot=terms,
            policy_snapshot=(
                {
                    "policy_id": policy.id,
                    "policy_name": policy.name,
                    "supplier_id": policy.supplier_id,
                    "brand_id": policy.brand_id,
                    "series_id": policy.series_id,
                    "product_id": policy.product_id,
                    "duration_months": int(duration_months),
                    "start_event": policy.start_event,
                    "maintenance_required": policy.maintenance_required,
                    "maintenance_interval_months": policy.maintenance_interval_months,
                    "grace_period_days": policy.grace_period_days,
                    "allowed_maintenance_provider": policy.allowed_maintenance_provider,
                    "terms": policy.terms,
                }
                if policy
                else {"duration_months": int(duration_months), "start_event": "installation"}
            ),
        )
        session.add(coverage)
        await session.flush()
        return coverage

    @classmethod
    def coverage_status(cls, coverage: EquipmentWarrantyCoverage, *, now: datetime | None = None) -> dict[str, Any]:
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
            "requires_manager_decision": maintenance_status == "overdue" and coverage.decision_status == "none",
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
            .order_by(EquipmentWarrantyCoverage.coverage_type, EquipmentWarrantyCoverage.id)
        )
        return [cls.to_item(item) for item in result.scalars().all()]

    @classmethod
    async def generate_maintenance_reminders(
        cls,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        from services.warranty_maintenance_service import WarrantyMaintenanceService

        return await WarrantyMaintenanceService.generate_reminders(session, now=now)

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
            await WarrantyMaintenanceService.restore_from_latest_maintenance(session, coverage=coverage)
        await session.commit()
        await session.refresh(coverage)
        return cls.to_item(coverage)

    @classmethod
    async def recalculate_after_maintenance(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        event_type: EquipmentServiceEventType,
        event_date: datetime,
        maintenance_provider: str | None,
    ) -> None:
        from services.warranty_maintenance_service import WarrantyMaintenanceService

        await WarrantyMaintenanceService.apply_maintenance_event(
            session,
            equipment_id=equipment_id,
            event_type=event_type,
            event_date=event_date,
            maintenance_provider=maintenance_provider,
        )
