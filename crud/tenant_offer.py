from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Product, Storefront, TenantAuditEvent, TenantOffer
from models.tenancy import TenantScope
from services.tenant_scope_service import storefront_scope_clause


class TenantOfferDAO:
    @staticmethod
    async def lock_scope_storefront(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> Storefront | None:
        result = await session.execute(
            select(Storefront)
            .where(
                Storefront.id == tenant_scope.storefront_id,
                Storefront.tenant_id == tenant_scope.tenant_id,
            )
            .with_for_update(of=Storefront)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def lock_product(
        session: AsyncSession,
        product_id: int,
    ) -> Product | None:
        result = await session.execute(
            select(Product)
            .where(Product.id == product_id)
            .with_for_update(of=Product)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_scope(
        session: AsyncSession,
        *,
        offer_id: int,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> TenantOffer | None:
        statement = select(TenantOffer).where(
            TenantOffer.id == offer_id,
            storefront_scope_clause(TenantOffer, tenant_scope),
        )
        if for_update:
            statement = statement.with_for_update(of=TenantOffer)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_product_for_scope(
        session: AsyncSession,
        *,
        product_id: int,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> TenantOffer | None:
        statement = select(TenantOffer).where(
            TenantOffer.product_id == product_id,
            storefront_scope_clause(TenantOffer, tenant_scope),
        )
        if for_update:
            statement = statement.with_for_update(of=TenantOffer)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_scope(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        offset: int,
        limit: int,
    ) -> tuple[list[tuple[TenantOffer, Product]], int]:
        scope_clause = storefront_scope_clause(TenantOffer, tenant_scope)
        rows = await session.execute(
            select(TenantOffer, Product)
            .join(Product, Product.id == TenantOffer.product_id)
            .where(scope_clause)
            .order_by(TenantOffer.updated_at.desc(), TenantOffer.id.desc())
            .offset(offset)
            .limit(limit)
        )
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(TenantOffer)
                    .where(scope_clause)
                )
            ).scalar_one()
        )
        return list(rows.all()), total

    @staticmethod
    async def get_product(
        session: AsyncSession,
        product_id: int,
    ) -> Product | None:
        return await session.get(Product, product_id)

    @staticmethod
    def add_offer(session: AsyncSession, offer: TenantOffer) -> None:
        session.add(offer)

    @staticmethod
    def add_audit_event(
        session: AsyncSession,
        event: TenantAuditEvent,
    ) -> None:
        session.add(event)

    @staticmethod
    async def list_audit_for_scope(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        offset: int,
        limit: int,
    ) -> tuple[list[TenantAuditEvent], int]:
        scope_clause = storefront_scope_clause(TenantAuditEvent, tenant_scope)
        rows = await session.execute(
            select(TenantAuditEvent)
            .where(scope_clause)
            .order_by(TenantAuditEvent.created_at.desc(), TenantAuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(TenantAuditEvent)
                    .where(scope_clause)
                )
            ).scalar_one()
        )
        return list(rows.scalars().all()), total
