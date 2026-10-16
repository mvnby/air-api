"""Delivery ACL follows the event's order scope, never the user's selected bot site."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from models import Order, OrderWorkStage
from models.tenancy import Tenant, Storefront, TenantMembership


async def task_notification_allowed(session: AsyncSession, staff_user, payload) -> bool:
    row = (
        await session.execute(
            select(
                Order.tenant_id,
                Order.storefront_id,
                OrderWorkStage.installer_id,
                TenantMembership.role,
            )
            .select_from(Order)
            .join(OrderWorkStage, OrderWorkStage.order_id == Order.id)
            .join(Tenant, Tenant.id == Order.tenant_id)
            .join(
                Storefront,
                (Storefront.id == Order.storefront_id)
                & (Storefront.tenant_id == Tenant.id),
            )
            .join(
                TenantMembership,
                (TenantMembership.tenant_id == Tenant.id)
                & (TenantMembership.staff_user_id == staff_user.id),
            )
            .where(
                Order.id == payload.order_id,
                OrderWorkStage.id == payload.stage_id,
                Tenant.status == "active",
                Storefront.status == "active",
                TenantMembership.status == "active",
            )
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None:
        return False
    if row.role not in {"owner", "admin", "manager", "installer"}:
        return False
    if row.installer_id != staff_user.legacy_installer_id:
        return False
    if payload.tenant_id is not None and payload.tenant_id != row.tenant_id:
        return False
    if payload.storefront_id is not None and payload.storefront_id != row.storefront_id:
        return False
    return True
