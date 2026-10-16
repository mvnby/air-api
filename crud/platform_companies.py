"""Batched company directory reads and locks for platform administration."""

from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StaffUser, Storefront, StorefrontDomain, Tenant, TenantMembership


class PlatformCompaniesDAO:
    @staticmethod
    async def list_tenants(session: AsyncSession, *, page: int, limit: int, search: str | None):
        query = select(Tenant)
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(or_(Tenant.display_name.ilike(term), Tenant.slug.ilike(term)))
        total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = list((await session.scalars(query.order_by(Tenant.is_system.desc(), Tenant.display_name, Tenant.id)
                                         .offset((page - 1) * limit).limit(limit))).all())
        return rows, total

    @staticmethod
    async def get_tenant(session: AsyncSession, tenant_id: int, *, lock: bool = False):
        query = select(Tenant).where(Tenant.id == tenant_id).execution_options(populate_existing=True)
        return await session.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def lock_staff(session: AsyncSession, staff_user_id: int):
        return await session.scalar(select(StaffUser).where(StaffUser.id == staff_user_id)
                                    .with_for_update().execution_options(populate_existing=True))

    @staticmethod
    async def details(session: AsyncSession, tenant_ids: list[int]):
        sites, domains, owners, counts = defaultdict(list), defaultdict(list), defaultdict(list), {}
        if not tenant_ids:
            return sites, domains, owners, counts
        site_rows = list((await session.scalars(select(Storefront).where(Storefront.tenant_id.in_(tenant_ids))
                                              .order_by(Storefront.is_default.desc(), Storefront.display_name, Storefront.id))).all())
        for site in site_rows:
            sites[site.tenant_id].append(site)
        if site_rows:
            for domain in (await session.scalars(select(StorefrontDomain)
                    .where(StorefrontDomain.storefront_id.in_([site.id for site in site_rows]))
                    .order_by(StorefrontDomain.is_primary.desc(), StorefrontDomain.hostname))).all():
                domains[domain.storefront_id].append(domain)
        live = (TenantMembership.tenant_id.in_(tenant_ids), TenantMembership.status == "active",
                StaffUser.status == "active", StaffUser.merged_into_staff_user_id.is_(None))
        for tenant_id, staff_id, name in (await session.execute(select(
                TenantMembership.tenant_id, StaffUser.id, StaffUser.display_name)
                .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
                .where(*live, TenantMembership.role == "owner")
                .order_by(StaffUser.display_name, StaffUser.id))).all():
            owners[tenant_id].append({"staff_user_id": staff_id, "display_name": name})
        for tenant_id, count in (await session.execute(select(TenantMembership.tenant_id, func.count())
                .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id).where(*live)
                .group_by(TenantMembership.tenant_id))).all():
            counts[tenant_id] = int(count)
        return sites, domains, owners, counts
