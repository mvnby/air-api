"""Locked price snapshots for public checkout."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.public_catalog import PublicCatalogDAO
from models import Product, Storefront, TenantOffer
from models.tenancy import TenantScope


@dataclass(frozen=True)
class LockedPublicCatalogProduct:
    product_id: int
    title: str
    unit_price: int
    currency: str


class PublicCatalogCheckoutDAO:
    @staticmethod
    async def lock_active_storefront_currency(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> str | None:
        """Lock the storefront before product rows to keep one lock order."""

        currency = await session.scalar(
            select(Storefront.currency)
            .where(
                Storefront.id == tenant_scope.storefront_id,
                Storefront.tenant_id == tenant_scope.tenant_id,
                Storefront.status == "active",
            )
            .with_for_update(read=True, of=Storefront)
        )
        normalized = str(currency or "").strip().upper()
        return normalized or None

    @staticmethod
    async def get_shared_snapshots_by_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: set[int],
    ) -> dict[int, LockedPublicCatalogProduct]:
        if not product_ids:
            return {}
        currency = await PublicCatalogCheckoutDAO.lock_active_storefront_currency(
            session,
            tenant_scope=tenant_scope,
        )
        if currency is None:
            return {}
        rows = (
            await session.execute(
                select(
                    Product.id,
                    Product.title,
                    Product.price,
                )
                .select_from(Product)
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                )
                .order_by(Product.id.asc())
                .with_for_update(read=True, of=Product)
            )
        ).all()
        return {
            int(product_id): LockedPublicCatalogProduct(
                product_id=int(product_id),
                title=str(title),
                unit_price=int(price),
                currency=currency,
            )
            for product_id, title, price in rows
        }

    @staticmethod
    async def get_offer_snapshots_by_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: set[int],
    ) -> dict[int, LockedPublicCatalogProduct]:
        if not product_ids:
            return {}
        currency = await PublicCatalogCheckoutDAO.lock_active_storefront_currency(
            session,
            tenant_scope=tenant_scope,
        )
        if currency is None:
            return {}
        rows = (
            await session.execute(
                select(
                    Product.id,
                    Product.title,
                    TenantOffer.price,
                )
                .select_from(Product)
                .join(TenantOffer, TenantOffer.product_id == Product.id)
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                    *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
                )
                .order_by(Product.id.asc())
                .with_for_update(
                    read=True,
                    of=(Product, TenantOffer),
                )
            )
        ).all()
        return {
            int(product_id): LockedPublicCatalogProduct(
                product_id=int(product_id),
                title=str(title),
                unit_price=int(price),
                currency=currency,
            )
            for product_id, title, price in rows
        }
