"""Persistence for explicit catalog delegation to company memberships."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StaffUser, Storefront, Tenant, TenantMembership


class ManagerAccessDAO:
    @staticmethod
    async def default_storefront_id(session: AsyncSession, tenant_id: int):
        return await session.scalar(select(Storefront.id).where(
            Storefront.tenant_id == tenant_id, Storefront.is_default.is_(True),
        ))

    @staticmethod
    async def list_memberships(session: AsyncSession, *, page: int, limit: int, search: str | None):
        statement = (
            select(TenantMembership, StaffUser.display_name, Tenant.display_name)
            .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(StaffUser.merged_into_staff_user_id.is_(None))
        )
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(or_(
                StaffUser.display_name.ilike(term), Tenant.display_name.ilike(term),
            ))
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await session.execute(
            statement.order_by(Tenant.display_name, StaffUser.display_name, TenantMembership.id)
            .offset((page - 1) * limit).limit(limit)
        )).all()
        return rows, int(total or 0)

    @staticmethod
    async def get_membership(session: AsyncSession, membership_id: int):
        return (await session.execute(
            select(TenantMembership, StaffUser.display_name, Tenant.display_name)
            .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.id == membership_id, StaffUser.merged_into_staff_user_id.is_(None))
            .with_for_update(of=TenantMembership)
        )).first()
