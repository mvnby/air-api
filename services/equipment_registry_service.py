from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerEquipment,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
)
from models.tenancy import TenantScope
from services.equipment_service import EquipmentService
from services.tenant_scope_service import tenant_or_legacy_owner_scope_clause


class EquipmentRegistryService:
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
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        if customer_id is not None and not await EquipmentService._ensure_customer_exists(
            session,
            customer_id,
            tenant_scope=tenant_scope,
        ):
            return None
        if customer_id is not None and customer_branch_id is not None:
            await EquipmentService._ensure_branch_for_customer(
                session,
                customer_id=customer_id,
                customer_branch_id=customer_branch_id,
            )

        filters = [tenant_or_legacy_owner_scope_clause(Customer, tenant_scope)]
        if customer_id is not None:
            filters.append(CustomerEquipment.customer_id == customer_id)
        if customer_branch_id is not None:
            filters.append(CustomerEquipment.customer_branch_id == customer_branch_id)
        if not include_archived:
            filters.append(CustomerEquipment.is_archived == False)
        search = EquipmentService._clean_optional_text(q)
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    CustomerEquipment.display_name.ilike(pattern),
                    CustomerEquipment.brand.ilike(pattern),
                    CustomerEquipment.model.ilike(pattern),
                    CustomerEquipment.serial.ilike(pattern),
                    CustomerEquipment.inventory_number.ilike(pattern),
                    CustomerEquipment.location_hint.ilike(pattern),
                    CustomerEquipment.customer.has(Customer.name.ilike(pattern)),
                    CustomerEquipment.customer_branch.has(CustomerBranch.delivery_address.ilike(pattern)),
                )
            )

        normalized_attention = EquipmentService._clean_optional_text(attention)
        if normalized_attention and normalized_attention != "all":
            now = datetime.now()
            soon = now + timedelta(days=30)
            if normalized_attention in {"maintenance_due_soon", "maintenance_overdue", "needs_decision"}:
                from services.warranty_service import WarrantyService

                coverage_result = await session.execute(
                    select(EquipmentWarrantyCoverage).where(
                        EquipmentWarrantyCoverage.maintenance_required == True,
                        EquipmentWarrantyCoverage.next_maintenance_due_at.is_not(None),
                        EquipmentWarrantyCoverage.decision_status != "voided",
                    )
                )
                matching_ids = set()
                for coverage in coverage_result.scalars().all():
                    status = WarrantyService.coverage_status(coverage, now=now)
                    if normalized_attention == "maintenance_due_soon" and status["maintenance_status"] == "due_soon":
                        matching_ids.add(int(coverage.equipment_id))
                    elif normalized_attention == "maintenance_overdue" and status["maintenance_status"] == "overdue":
                        matching_ids.add(int(coverage.equipment_id))
                    elif normalized_attention == "needs_decision" and status["requires_manager_decision"]:
                        matching_ids.add(int(coverage.equipment_id))
                selected_filter = CustomerEquipment.id.in_(matching_ids or {-1})
                if normalized_attention == "needs_decision":
                    covered_equipment = select(EquipmentWarrantyCoverage.equipment_id).where(
                        EquipmentWarrantyCoverage.decision_status != "voided"
                    )
                    selected_filter = or_(
                        selected_filter,
                        ~CustomerEquipment.id.in_(covered_equipment),
                    )
                filters.append(selected_filter)
            else:
                attention_conditions = {
                    "warranty_expiring": (
                        EquipmentWarrantyCoverage.expires_at >= now,
                        EquipmentWarrantyCoverage.expires_at <= soon,
                        EquipmentWarrantyCoverage.decision_status != "voided",
                    ),
                    "warranty_expired": (
                        EquipmentWarrantyCoverage.expires_at < now,
                        EquipmentWarrantyCoverage.decision_status != "voided",
                    ),
                }
                selected_conditions = attention_conditions.get(normalized_attention)
                if selected_conditions is None:
                    raise ValueError("Unsupported equipment attention filter")
                matching_equipment_ids = select(EquipmentWarrantyCoverage.equipment_id).where(*selected_conditions)
                filters.append(CustomerEquipment.id.in_(matching_equipment_ids))

        count_result = await session.execute(
            select(func.count(CustomerEquipment.id))
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .where(*filters)
        )
        total = int(count_result.scalar() or 0)
        result = await session.execute(
            select(CustomerEquipment)
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .options(
                selectinload(CustomerEquipment.customer),
                selectinload(CustomerEquipment.customer_branch),
            )
            .where(*filters)
            .order_by(CustomerEquipment.is_archived.asc(), CustomerEquipment.created_at.desc(), CustomerEquipment.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        equipment_rows = list(result.scalars().all())
        equipment_ids = [int(item.id or 0) for item in equipment_rows]
        coverages_by_equipment: dict[int, list[EquipmentWarrantyCoverage]] = {item_id: [] for item_id in equipment_ids}
        last_service_by_equipment: dict[int, datetime] = {}
        if equipment_ids:
            coverage_result = await session.execute(
                select(EquipmentWarrantyCoverage).where(
                    EquipmentWarrantyCoverage.equipment_id.in_(equipment_ids)
                )
            )
            for coverage in coverage_result.scalars().all():
                coverages_by_equipment.setdefault(int(coverage.equipment_id), []).append(coverage)
            history_result = await session.execute(
                select(
                    EquipmentServiceHistory.equipment_id,
                    func.max(EquipmentServiceHistory.event_date),
                )
                .where(EquipmentServiceHistory.equipment_id.in_(equipment_ids))
                .group_by(EquipmentServiceHistory.equipment_id)
            )
            last_service_by_equipment = {
                int(equipment_id): event_date
                for equipment_id, event_date in history_result.all()
                if event_date is not None
            }

        from services.warranty_service import WarrantyService

        now = datetime.now()
        items = []
        for equipment in equipment_rows:
            equipment_id = int(equipment.id or 0)
            data = EquipmentService._to_equipment_item(equipment)
            equipment_coverages = coverages_by_equipment.get(equipment_id, [])
            EquipmentService._apply_coverage_summary(data, equipment_coverages, now=now)
            customer = equipment.customer
            branch = equipment.customer_branch
            data.update(
                {
                    "customer_name": customer.name if customer else None,
                    "customer_phone": customer.phone if customer else None,
                    "branch_name": branch.name if branch else None,
                    "branch_address": branch.delivery_address if branch else equipment.location_hint,
                    "service_contact_name": (
                        branch.contact_name if branch and branch.contact_name else (customer.name if customer else None)
                    ),
                    "service_contact_phone": (
                        branch.contact_phone if branch and branch.contact_phone else (customer.phone if customer else None)
                    ),
                    "last_service_at": last_service_by_equipment.get(equipment_id),
                }
            )
            next_due_values = []
            attention_reasons: set[str] = set()
            if not equipment_coverages:
                attention_reasons.add("needs_decision")
            for coverage in equipment_coverages:
                status = WarrantyService.coverage_status(coverage, now=now)
                if coverage.next_maintenance_due_at is not None:
                    next_due_values.append(EquipmentService._normalize_naive_datetime(coverage.next_maintenance_due_at))
                if status["maintenance_status"] == "overdue":
                    attention_reasons.add("maintenance_overdue")
                elif status["maintenance_status"] == "due_soon":
                    attention_reasons.add("maintenance_due_soon")
                if status["requires_manager_decision"]:
                    attention_reasons.add("needs_decision")
                if status["time_status"] == "expired":
                    attention_reasons.add("warranty_expired")
                elif (
                    status["time_status"] == "active"
                    and coverage.expires_at is not None
                    and EquipmentService._normalize_naive_datetime(coverage.expires_at) <= now + timedelta(days=30)
                ):
                    attention_reasons.add("warranty_expiring")
            data["next_maintenance_due_at"] = min((value for value in next_due_values if value), default=None)
            data["attention_reasons"] = sorted(attention_reasons)
            items.append(data)
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
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
        if not equipment:
            return None
        history = await EquipmentService.list_history(
            session,
            equipment_id=equipment_id,
            page=1,
            limit=history_limit,
            tenant_scope=tenant_scope,
        )
        components = await EquipmentService.list_components(
            session,
            equipment_id=equipment_id,
            include_archived=True,
            tenant_scope=tenant_scope,
        )
        data = EquipmentService._to_equipment_item(equipment)
        data["components"] = components
        data["recent_history"] = history["items"]
        from services.equipment_link_service import EquipmentLinkService
        from services.warranty_service import WarrantyService

        coverage_result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == equipment_id
            )
        )
        coverage_models = list(coverage_result.scalars().all())
        data["coverages"] = [WarrantyService.to_item(item) for item in coverage_models]
        EquipmentService._apply_coverage_summary(data, coverage_models)
        data["linked_orders"] = await EquipmentLinkService.list_linked_orders(
            session,
            equipment_id=equipment_id,
            tenant_scope=tenant_scope,
        )
        return data
