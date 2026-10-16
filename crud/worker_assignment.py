"""Scoped persistence for explicit work access; payroll links never grant access."""
from sqlalchemy import and_, exists, func, or_, select
from models import Order, OrderInstaller, OrderWorkAssignment, OrderWorkStage, StaffUser, TenantMembership, TenantWorkerProfile

WORKER_ROLES = frozenset({'owner', 'admin', 'manager', 'installer'})
ACTIVE_STAGES = ('planned', 'in_progress')


class WorkerAssignmentDAO:
    @staticmethod
    def visible(scope, staff_id, *, include_completed=False):
        return (select(OrderWorkAssignment)
            .join(TenantWorkerProfile, TenantWorkerProfile.id == OrderWorkAssignment.worker_profile_id)
            .join(StaffUser, StaffUser.id == TenantWorkerProfile.staff_user_id)
            .join(TenantMembership, and_(TenantMembership.tenant_id == TenantWorkerProfile.tenant_id,
                                         TenantMembership.staff_user_id == StaffUser.id))
            .join(Order, Order.id == OrderWorkAssignment.order_id)
            .outerjoin(OrderWorkStage, OrderWorkStage.id == OrderWorkAssignment.work_stage_id)
            .where(OrderWorkAssignment.tenant_id == scope.tenant_id,
                   OrderWorkAssignment.storefront_id == scope.storefront_id,
                   Order.tenant_id == scope.tenant_id, Order.storefront_id == scope.storefront_id,
                   Order.status != 'closed', OrderWorkAssignment.revoked_at.is_(None),
                   TenantWorkerProfile.staff_user_id == staff_id, TenantWorkerProfile.status == 'active',
                   StaffUser.status == 'active', StaffUser.merged_into_staff_user_id.is_(None),
                   TenantMembership.status == 'active', TenantMembership.role.in_(WORKER_ROLES),
                   or_(OrderWorkAssignment.work_stage_id.is_(None), OrderWorkStage.status.in_((*ACTIVE_STAGES, 'completed') if include_completed else ACTIVE_STAGES)),
                   or_(OrderWorkAssignment.source != 'legacy_stage',
                       OrderWorkStage.installer_id == TenantWorkerProfile.canonical_legacy_installer_id),
                   or_(OrderWorkAssignment.source != 'legacy_order', exists(select(OrderInstaller.order_id).where(
                       OrderInstaller.order_id == OrderWorkAssignment.order_id,
                       OrderInstaller.installer_id == TenantWorkerProfile.canonical_legacy_installer_id)))))

    @classmethod
    async def visible_list(cls, session, scope, staff_id, page, limit):
        statement = cls.visible(scope, staff_id)
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list((await session.scalars(statement.order_by(OrderWorkAssignment.id.desc())
            .offset((page - 1) * limit).limit(limit).execution_options(populate_existing=True))).all())
        return rows, int(total or 0)

    @staticmethod
    async def profile(session, tenant_id, staff_id, *, lock=False):
        statement = select(TenantWorkerProfile).where(TenantWorkerProfile.tenant_id == tenant_id,
            TenantWorkerProfile.staff_user_id == staff_id).execution_options(populate_existing=True)
        return await session.scalar(statement.with_for_update(read=True) if lock else statement)

    @staticmethod
    async def candidates(session, tenant_id, page, limit):
        statement = select(StaffUser).join(TenantMembership, TenantMembership.staff_user_id == StaffUser.id).outerjoin(
            TenantWorkerProfile, and_(TenantWorkerProfile.tenant_id == tenant_id, TenantWorkerProfile.staff_user_id == StaffUser.id)
        ).where(TenantMembership.tenant_id == tenant_id, TenantMembership.status == 'active',
            TenantMembership.role.in_(WORKER_ROLES), StaffUser.status == 'active', StaffUser.merged_into_staff_user_id.is_(None),
            or_(TenantWorkerProfile.id.is_(None), TenantWorkerProfile.status == 'active'))
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        return list((await session.scalars(statement.order_by(StaffUser.display_name, StaffUser.id)
            .offset((page - 1) * limit).limit(limit))).all()), int(total or 0)
