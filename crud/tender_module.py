from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import LeadSource, Order, Storefront, TenantTenderModule
from models.tenancy import TenantScope
from services.tenant_scope_service import storefront_scope_clause


class TenderModuleDAO:
    @staticmethod
    async def get(session: AsyncSession, tenant_id: int) -> TenantTenderModule | None:
        return await session.get(TenantTenderModule, tenant_id, populate_existing=True)

    @staticmethod
    async def default_storefront_id(session: AsyncSession, tenant_id: int) -> int | None:
        return await session.scalar(select(Storefront.id).where(
            Storefront.tenant_id == tenant_id, Storefront.is_default.is_(True),
        ))

    @staticmethod
    async def recent_orders(session: AsyncSession, scope: TenantScope):
        rows = await session.execute(select(Order.id, Order.technical_meta).where(
            storefront_scope_clause(Order, scope), Order.lead_source == LeadSource.BELZAKUPKI,
        ).order_by(Order.created_at.desc(), Order.id.desc()).limit(20))
        return rows.all()
