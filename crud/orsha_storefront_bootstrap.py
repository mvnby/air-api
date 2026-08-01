from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    Lead,
    Order,
    Product,
    Storefront,
    StorefrontDomain,
    Tenant,
    TenantOffer,
)


class OrshaStorefrontBootstrapDAO:
    LOCK_KEY = "mvn:orsha-storefront-bootstrap:v1"

    @staticmethod
    async def try_acquire_transaction_lock(session: AsyncSession) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": OrshaStorefrontBootstrapDAO.LOCK_KEY},
        )
        return bool(acquired)

    @staticmethod
    async def get_tenant(
        session: AsyncSession,
        *,
        slug: str,
        for_update: bool,
    ) -> Tenant | None:
        statement = select(Tenant).where(Tenant.slug == slug)
        if for_update:
            statement = statement.with_for_update(of=Tenant)
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def get_storefront(
        session: AsyncSession,
        *,
        tenant_id: int,
        slug: str,
        for_update: bool,
    ) -> Storefront | None:
        statement = select(Storefront).where(
            Storefront.tenant_id == tenant_id,
            Storefront.slug == slug,
        )
        if for_update:
            statement = statement.with_for_update(of=Storefront)
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def get_domain_by_hostname(
        session: AsyncSession,
        *,
        hostname: str,
        for_update: bool,
    ) -> StorefrontDomain | None:
        statement = select(StorefrontDomain).where(
            StorefrontDomain.hostname == hostname
        )
        if for_update:
            statement = statement.with_for_update(of=StorefrontDomain)
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def list_domains(
        session: AsyncSession,
        *,
        storefront_id: int,
        for_update: bool,
        limit: int,
    ) -> list[StorefrontDomain]:
        statement = (
            select(StorefrontDomain)
            .where(StorefrontDomain.storefront_id == storefront_id)
            .order_by(StorefrontDomain.id.asc())
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update(of=StorefrontDomain)
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    async def list_offers_with_products(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        for_update: bool,
        limit: int,
    ) -> list[tuple[TenantOffer, Product]]:
        statement = (
            select(TenantOffer, Product)
            .join(Product, Product.id == TenantOffer.product_id)
            .where(
                TenantOffer.tenant_id == tenant_id,
                TenantOffer.storefront_id == storefront_id,
            )
            .order_by(TenantOffer.product_id.asc())
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update(of=TenantOffer)
        return list((await session.execute(statement)).all())

    @staticmethod
    async def resolve_products(
        session: AsyncSession,
        *,
        product_ids: Iterable[int],
        product_slugs: Iterable[str],
        for_update: bool,
    ) -> list[Product]:
        ids = tuple(sorted({int(value) for value in product_ids}))
        slugs = tuple(sorted({str(value) for value in product_slugs}))
        clauses = []
        if ids:
            clauses.append(Product.id.in_(ids))
        if slugs:
            clauses.append(Product.slug.in_(slugs))
        if not clauses:
            return []
        statement = select(Product).where(or_(*clauses)).order_by(Product.id.asc())
        if for_update:
            statement = statement.with_for_update(of=Product)
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    async def crm_counts(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int | None,
    ) -> dict[str, int]:
        customer_count = int(
            (
                await session.execute(
                    select(func.count(Customer.id)).where(
                        Customer.tenant_id == tenant_id
                    )
                )
            ).scalar_one()
        )
        if storefront_id is None:
            return {"customers_in_tenant": customer_count, "leads": 0, "orders": 0}
        lead_count = int(
            (
                await session.execute(
                    select(func.count(Lead.id)).where(
                        Lead.tenant_id == tenant_id,
                        Lead.storefront_id == storefront_id,
                    )
                )
            ).scalar_one()
        )
        order_count = int(
            (
                await session.execute(
                    select(func.count(Order.id)).where(
                        Order.tenant_id == tenant_id,
                        Order.storefront_id == storefront_id,
                    )
                )
            ).scalar_one()
        )
        return {
            "customers_in_tenant": customer_count,
            "leads": lead_count,
            "orders": order_count,
        }
