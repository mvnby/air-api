"""Explicit new Manager assignments bridge canonical legacy executors only.

Imports and unchanged payroll edits never create grants. Synchronization may only
revoke grants it owns; a separately confirmed manual assignment remains intact.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from models import Order, OrderWorkAssignment, StaffUser, Tenant, Storefront
from crud.worker_assignment import ACTIVE_STAGES, WorkerAssignmentDAO
from services.order_responsibility_service import OrderResponsibilityService
from services.worker_assignment_service import WorkerAssignmentService


class WorkerAssignmentLegacySync:
    @staticmethod
    async def prepare(session, scope, installer_ids=()):
        # Always before Order locks/first child INSERT, including empty removals.
        ids = {int(value) for value in installer_ids if value is not None}
        candidates = list((await session.scalars(select(StaffUser).where(StaffUser.legacy_installer_id.in_(ids)))).all()) if ids else []
        _, staff, members = await OrderResponsibilityService._fence(session, scope, [row.id for row in candidates], mutation=True)
        tenant = await session.get(Tenant, scope.tenant_id)
        site = await session.get(Storefront, scope.storefront_id)
        if not tenant.is_system or tenant.slug != "mvn" or site.slug != "main":
            return {}
        profiles = {}
        for row in sorted(candidates, key=lambda item: item.id):
            user = staff.get(row.id)
            if WorkerAssignmentService.eligible(user, members.get(row.id)):
                existing = await WorkerAssignmentDAO.profile(session, scope.tenant_id, user.id, lock=True)
                if existing is not None and existing.status != "active":
                    # Workspace suspension must not break historical payroll edits.
                    continue
                profile = await WorkerAssignmentService.ensure_profile(session, scope, user)
                profiles[user.legacy_installer_id] = profile
        return profiles

    @staticmethod
    async def sync(session, scope, order_id, prepared, *, previous_ids, current_ids, stage=None):
        source = 'legacy_stage' if stage is not None else 'legacy_order'
        stage_id = stage.id if stage is not None else None
        order = await session.get(Order, order_id)
        active = order.status != 'closed' and (stage is None or stage.status in ACTIVE_STAGES)
        current = set(current_ids)
        rows = list((await session.scalars(select(OrderWorkAssignment).where(
            OrderWorkAssignment.tenant_id == scope.tenant_id, OrderWorkAssignment.storefront_id == scope.storefront_id,
            OrderWorkAssignment.order_id == order_id, OrderWorkAssignment.work_stage_id == stage_id,
            OrderWorkAssignment.source == source, OrderWorkAssignment.revoked_at.is_(None)
        ).with_for_update().execution_options(populate_existing=True))).all())
        from models import TenantWorkerProfile
        for row in rows:
            profile = await session.get(TenantWorkerProfile, row.worker_profile_id)
            if profile.canonical_legacy_installer_id not in current:
                row.revoked_at = datetime.now(timezone.utc)
                row.version += 1
                WorkerAssignmentService.audit(session, scope, None, row, 'work_assignment.legacy_revoked', {'source': source, 'version': row.version})
        await session.flush()
        for installer_id in sorted((current - set(previous_ids)) if active else set()):
            profile = prepared.get(installer_id)
            if profile is None:
                continue
            existing = await session.scalar(select(OrderWorkAssignment.id).where(OrderWorkAssignment.order_id == order_id,
                OrderWorkAssignment.work_stage_id == stage_id, OrderWorkAssignment.worker_profile_id == profile.id,
                OrderWorkAssignment.revoked_at.is_(None)))
            if existing is not None:
                continue
            row = OrderWorkAssignment(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                order_id=order_id, work_stage_id=stage_id, worker_profile_id=profile.id, source=source)
            session.add(row)
            await session.flush()
            WorkerAssignmentService.audit(session, scope, None, row, 'work_assignment.legacy_created', {'source': source, 'staff_user_id': profile.staff_user_id})
        await session.flush()
