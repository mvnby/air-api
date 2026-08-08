"""Small tenant website communication fixtures shared by unit tests."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models import StaffUser, Storefront, Tenant, TenantMembership


TENANT_WEBSITE_SCOPE_TABLES = (
    Tenant.__table__,
    Storefront.__table__,
)


async def ensure_tenant_website_scope(
    session: AsyncSession,
    *,
    tenant_id: int = 1,
    storefront_id: int = 1,
) -> None:
    if await session.get(Tenant, tenant_id) is None:
        session.add(
            Tenant(
                id=tenant_id,
                slug=f"tenant-{tenant_id}",
                display_name=f"Tenant {tenant_id}",
                status="active",
            )
        )
    if await session.get(Storefront, storefront_id) is None:
        session.add(
            Storefront(
                id=storefront_id,
                tenant_id=tenant_id,
                slug=f"storefront-{storefront_id}",
                display_name=f"Storefront {storefront_id}",
                status="active",
                is_default=True,
            )
        )
    await session.flush()


async def add_tenant_members(
    session: AsyncSession,
    *staff_users: StaffUser,
    tenant_id: int = 1,
    role: str = "owner",
) -> None:
    session.add_all(staff_users)
    await session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant_id,
                staff_user_id=int(staff_user.id or 0),
                role=role,
                status="active",
            )
            for staff_user in staff_users
        ]
    )
