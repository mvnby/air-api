"""Warranty policy resolution and immutable equipment coverage snapshots."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Brand,
    CustomerEquipment,
    EquipmentServiceEventType,
    EquipmentWarrantyCoverage,
    Product,
    ProductSeries,
    Supplier,
    WarrantyPolicy,
)
from models.tenancy import TenantScope
from services.catalog_revision_service import CatalogRevisionService
from services.warranty_coverage_service import WarrantyCoverageService
from services.warranty_policy_resolver import WarrantyPolicyResolver
from crud.warranty_policy import WarrantyPolicyStore


class WarrantyService(WarrantyPolicyStore):
    COVERAGE_TYPES = {"supplier", "mvn_work", "legacy"}
    DECISIONS = WarrantyCoverageService.DECISIONS

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
        series_ids_by_policy = await cls._policy_series_ids(session, policies)
        if series_id is not None:
            policies = [
                policy
                for policy in policies
                if int(series_id) in series_ids_by_policy.get(int(policy.id or 0), [])
            ]
        scope_names = await cls._policy_scope_names(session, policies, series_ids_by_policy)
        return [
            cls.policy_to_item(
                item,
                scope_names=scope_names,
                series_ids=series_ids_by_policy.get(int(item.id or 0), []),
            )
            for item in policies
        ]

    @classmethod
    async def create_policy(cls, session: AsyncSession, *, payload: dict[str, Any]) -> dict[str, Any]:
        values = cls._validated_policy_values(payload, partial=False)
        uses_series_ids = "series_ids" in values
        selected_series_ids = cls._normalized_series_ids(values.pop("series_ids", None)) if uses_series_ids else (
            [] if values.get("series_id") is None else [int(values["series_id"])]
        )
        if uses_series_ids:
            values["series_id"] = selected_series_ids[0] if selected_series_ids else None
        if not any(values.get(key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(
            session,
            values,
            selected_series_ids=selected_series_ids,
            infer_brand_from_series=uses_series_ids,
        )
        if values.get("maintenance_required") and values.get("maintenance_interval_months") is None:
            values["maintenance_interval_months"] = 12
        policy = WarrantyPolicy(**values)
        session.add(policy)
        await session.flush()
        await cls._replace_policy_series(
            session,
            policy_id=int(policy.id or 0),
            series_ids=selected_series_ids,
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="warranty_policy_created",
        )
        await session.commit()
        await session.refresh(policy)
        series_ids_by_policy = await cls._policy_series_ids(session, [policy])
        scope_names = await cls._policy_scope_names(session, [policy], series_ids_by_policy)
        return cls.policy_to_item(
            policy,
            scope_names=scope_names,
            series_ids=series_ids_by_policy[int(policy.id or 0)],
        )

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
        existing_series_ids = (await cls._policy_series_ids(session, [policy])).get(int(policy.id or 0), [])
        uses_series_ids = "series_ids" in values
        uses_legacy_series_id = "series_id" in values
        if uses_series_ids:
            selected_series_ids = cls._normalized_series_ids(values.pop("series_ids"))
        elif uses_legacy_series_id:
            selected_series_ids = [] if values.get("series_id") is None else [int(values["series_id"])]
        else:
            selected_series_ids = existing_series_ids

        candidate = {
            field: getattr(policy, field)
            for field in (
                "name", "coverage_type", "supplier_id", "brand_id", "series_id", "product_id",
                "duration_months", "start_event", "maintenance_required", "maintenance_interval_months",
                "grace_period_days", "allowed_maintenance_provider", "terms", "effective_from",
                "effective_until", "is_active",
            )
        }
        candidate.update(values)
        if uses_series_ids or uses_legacy_series_id:
            candidate["series_id"] = selected_series_ids[0] if selected_series_ids else None
        if not any(candidate.get(key) is not None for key in ("supplier_id", "brand_id", "series_id", "product_id")):
            raise ValueError("Warranty policy must target a supplier, brand, series or product")
        await cls._validate_policy_scope(
            session,
            candidate,
            selected_series_ids=selected_series_ids,
            infer_brand_from_series=uses_series_ids,
        )
        if candidate.get("maintenance_required") and candidate.get("maintenance_interval_months") is None:
            candidate["maintenance_interval_months"] = 12
        for field, value in candidate.items():
            if getattr(policy, field) != value:
                setattr(policy, field, value)
        policy.updated_at = datetime.now()
        session.add(policy)
        if uses_series_ids or uses_legacy_series_id:
            await cls._replace_policy_series(
                session,
                policy_id=int(policy.id or 0),
                series_ids=selected_series_ids,
            )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="warranty_policy_updated",
        )
        await session.commit()
        await session.refresh(policy)
        series_ids_by_policy = await cls._policy_series_ids(session, [policy])
        scope_names = await cls._policy_scope_names(session, [policy], series_ids_by_policy)
        return cls.policy_to_item(
            policy,
            scope_names=scope_names,
            series_ids=series_ids_by_policy[int(policy.id or 0)],
        )

    @staticmethod
    async def _validate_policy_scope(
        session: AsyncSession,
        values: dict[str, Any],
        *,
        selected_series_ids: list[int],
        infer_brand_from_series: bool = False,
    ) -> None:
        supplier_id = values.get("supplier_id")
        brand_id = values.get("brand_id")
        product_id = values.get("product_id")
        if supplier_id is not None and not await session.get(Supplier, int(supplier_id)):
            raise ValueError("Warranty policy supplier not found")
        brand = await session.get(Brand, int(brand_id)) if brand_id is not None else None
        if brand_id is not None and not brand:
            raise ValueError("Warranty policy brand not found")
        series_rows: list[ProductSeries] = []
        if selected_series_ids:
            result = await session.execute(
                select(ProductSeries).where(ProductSeries.id.in_(selected_series_ids))
            )
            series_by_id = {int(series.id): series for series in result.scalars().all() if series.id is not None}
            missing = [series_id for series_id in selected_series_ids if series_id not in series_by_id]
            if missing:
                raise ValueError("Warranty policy series not found")
            series_rows = [series_by_id[series_id] for series_id in selected_series_ids]
            selected_brand_ids = {int(series.brand_id) for series in series_rows if series.brand_id is not None}
            if len(selected_brand_ids) != 1 or any(series.brand_id is None for series in series_rows):
                raise ValueError("Warranty policy series must belong to one brand")
            selected_brand_id = next(iter(selected_brand_ids))
            if brand_id is not None and int(brand_id) != selected_brand_id:
                raise ValueError("Warranty policy series does not belong to the selected brand")
            if infer_brand_from_series and brand_id is None:
                values["brand_id"] = selected_brand_id
                brand_id = selected_brand_id
        product = await session.get(Product, int(product_id)) if product_id is not None else None
        if product_id is not None and not product:
            raise ValueError("Warranty policy product not found")
        if product and brand_id is not None and int(product.brand_id or 0) != int(brand_id):
            raise ValueError("Warranty policy product does not belong to the selected brand")
        if product and selected_series_ids and int(product.series_id or 0) not in selected_series_ids:
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
        return await WarrantyPolicyResolver.resolve_one(
            session,
            product=product,
            supplier_id=supplier_id,
            coverage_type=coverage_type,
            at=at,
        )

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
        policy_series_ids = (
            (await cls._policy_series_ids(session, [policy])).get(int(policy.id or 0), [])
            if policy
            else []
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
                "series_ids": policy_series_ids,
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
        policy_series_ids = (
            (await cls._policy_series_ids(session, [policy])).get(int(policy.id or 0), [])
            if policy
            else []
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
                    "series_ids": policy_series_ids,
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
        return WarrantyCoverageService.coverage_status(coverage, now=now)

    @classmethod
    def to_item(cls, coverage: EquipmentWarrantyCoverage) -> dict[str, Any]:
        return WarrantyCoverageService.to_item(coverage)

    @classmethod
    async def list_coverages(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]] | None:
        return await WarrantyCoverageService.list_coverages(
            session,
            equipment_id=equipment_id,
            tenant_scope=tenant_scope,
        )

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
        return await WarrantyCoverageService.record_decision(
            session,
            coverage_id=coverage_id,
            action=action,
            reason=reason,
            decided_by=decided_by,
            tenant_scope=tenant_scope,
        )

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
