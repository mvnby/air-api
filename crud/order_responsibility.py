"""Minimal responsibility projections and ordered transaction fences."""

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from models import Order, StaffUser, Storefront, Tenant, TenantMembership
from services.tenant_scope_service import storefront_scope_clause

ELIGIBLE_ROLES = frozenset({"owner", "admin", "manager"})


class OrderResponsibilityDAO:
    @staticmethod
    async def context(session: AsyncSession, scope, staff_ids, *, lock: bool = True):
        def fresh(statement):
            statement = statement.execution_options(populate_existing=True)
            return statement.with_for_update(read=True) if lock else statement
        tenant = await session.scalar(fresh(select(Tenant).where(Tenant.id == scope.tenant_id)))
        ids = sorted({int(value) for value in staff_ids if value is not None})
        staff = list((await session.scalars(fresh(select(StaffUser).where(StaffUser.id.in_(ids))
            .order_by(StaffUser.id)))).all())
        memberships = list((await session.scalars(fresh(select(TenantMembership).where(
            TenantMembership.tenant_id == scope.tenant_id,
            TenantMembership.staff_user_id.in_(ids),
        ).order_by(TenantMembership.staff_user_id)))).all())
        site = await session.scalar(fresh(select(Storefront).where(
            Storefront.id == scope.storefront_id, Storefront.tenant_id == scope.tenant_id,
        )))
        return tenant, site, {row.id: row for row in staff}, {row.staff_user_id: row for row in memberships}

    @staticmethod
    async def lock_order(session: AsyncSession, order_id: int, scope):
        return await session.scalar(select(Order).where(
            Order.id == order_id, storefront_scope_clause(Order, scope),
        ).with_for_update().execution_options(populate_existing=True))

    @staticmethod
    def person_statement():
        return select(
            StaffUser.id, StaffUser.display_name, StaffUser.avatar_version,
            StaffUser.status.label("staff_status"), StaffUser.merged_into_staff_user_id,
            TenantMembership.tenant_id, TenantMembership.status.label("membership_status"),
            TenantMembership.role,
        ).join(TenantMembership, TenantMembership.staff_user_id == StaffUser.id)

    @classmethod
    async def people(cls, session: AsyncSession, pairs):
        if not pairs:
            return []
        return (await session.execute(cls.person_statement().where(
            tuple_(TenantMembership.tenant_id, StaffUser.id).in_(sorted(pairs)),
        ))).all()

    @classmethod
    async def candidates(cls, session: AsyncSession, *, tenant_id: int, page: int, limit: int):
        statement = cls.person_statement().where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active", TenantMembership.role.in_(ELIGIBLE_ROLES),
            StaffUser.status == "active", StaffUser.merged_into_staff_user_id.is_(None),
        )
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await session.execute(statement.order_by(StaffUser.display_name, StaffUser.id)
            .offset((page - 1) * limit).limit(limit))).all()
        return rows, int(total or 0)
