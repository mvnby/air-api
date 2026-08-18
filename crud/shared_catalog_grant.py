from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Product,
    Storefront,
    Tenant,
    TenantAuditEvent,
    TenantCatalogGrant,
    TenantOffer,
)


class SharedCatalogGrantDAO:
    LOCK_NAMESPACE = "mvn:shared-catalog-grant:v1"

    @classmethod
    async def try_acquire_transaction_lock(
        cls,
        session: AsyncSession,
        *,
        tenant_slug: str,
        storefront_slug: str,
    ) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        lock_key = (
            f"{cls.LOCK_NAMESPACE}:scope:{tenant_slug}:{storefront_slug}"
        )
        return bool(
            await session.scalar(
                text(
                    "SELECT pg_try_advisory_xact_lock("
                    "hashtextextended(:lock_key, 0))"
                ),
                {"lock_key": lock_key},
            )
        )

    @staticmethod
    async def get_scope(
        session: AsyncSession,
        *,
        tenant_slug: str,
        storefront_slug: str,
        for_update: bool,
    ) -> tuple[Tenant, Storefront] | None:
        statement = (
            select(Tenant, Storefront)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(
                Tenant.slug == tenant_slug,
                Storefront.slug == storefront_slug,
            )
        )
        if for_update:
            statement = statement.with_for_update(of=(Tenant, Storefront))
        return (await session.execute(statement)).one_or_none()

    @staticmethod
    async def get_grant(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        for_update: bool,
    ) -> TenantCatalogGrant | None:
        statement = select(TenantCatalogGrant).where(
            TenantCatalogGrant.tenant_id == tenant_id,
            TenantCatalogGrant.storefront_id == storefront_id,
        )
        if for_update:
            statement = statement.with_for_update(of=TenantCatalogGrant)
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def list_projection_rows(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        grant_id: int | None,
        desired_status: str,
    ) -> list[tuple[Product, TenantOffer | None]]:
        offer_join = and_(
            TenantOffer.product_id == Product.id,
            TenantOffer.tenant_id == tenant_id,
            TenantOffer.storefront_id == storefront_id,
        )
        statement = (
            select(Product, TenantOffer)
            .outerjoin(TenantOffer, offer_join)
            .order_by(Product.id.asc())
        )
        if desired_status == "active":
            conditions = [Product.is_published.is_(True)]
            if grant_id is not None:
                conditions.append(TenantOffer.catalog_grant_id == grant_id)
            statement = statement.where(or_(*conditions))
        elif grant_id is None:
            return []
        else:
            statement = statement.where(TenantOffer.catalog_grant_id == grant_id)
        return list((await session.execute(statement)).all())

    @staticmethod
    async def lock_products(
        session: AsyncSession,
        product_ids: Iterable[int],
    ) -> None:
        ids = tuple(sorted({int(value) for value in product_ids}))
        if not ids:
            return
        await session.execute(
            select(Product)
            .where(Product.id.in_(ids))
            .order_by(Product.id.asc())
            .with_for_update(of=Product)
        )

    @staticmethod
    async def lock_offers(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
        product_ids: Iterable[int],
    ) -> None:
        ids = tuple(sorted({int(value) for value in product_ids}))
        if not ids:
            return
        await session.execute(
            select(TenantOffer)
            .where(
                TenantOffer.tenant_id == tenant_id,
                TenantOffer.storefront_id == storefront_id,
                TenantOffer.product_id.in_(ids),
            )
            .order_by(TenantOffer.product_id.asc(), TenantOffer.id.asc())
            .with_for_update(of=TenantOffer)
        )

    @staticmethod
    def add_audit_event(
        session: AsyncSession,
        event: TenantAuditEvent,
    ) -> None:
        session.add(event)


__all__ = ["SharedCatalogGrantDAO"]
