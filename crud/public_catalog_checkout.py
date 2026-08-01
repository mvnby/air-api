"""Locked price snapshots for public checkout."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.public_catalog import PublicCatalogDAO
from models import Product, TenantOffer
from models.tenancy import TenantScope


class PublicCatalogCheckoutDAO:
    @staticmethod
    async def get_shared_prices_by_ids(
        session: AsyncSession,
        *,
        product_ids: set[int],
    ) -> dict[int, int]:
        if not product_ids:
            return {}
        rows = (
            await session.execute(
                select(Product.id, Product.price)
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                )
                .order_by(Product.id.asc())
                .with_for_update(read=True, of=Product)
            )
        ).all()
        return {int(product_id): int(price) for product_id, price in rows}

    @staticmethod
    async def get_offer_prices_by_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: set[int],
    ) -> dict[int, int]:
        if not product_ids:
            return {}
        rows = (
            await session.execute(
                select(Product.id, TenantOffer.price)
                .select_from(Product)
                .join(TenantOffer, TenantOffer.product_id == Product.id)
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                    *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
                )
                .order_by(Product.id.asc())
                .with_for_update(read=True, of=(Product, TenantOffer))
            )
        ).all()
        return {int(product_id): int(price) for product_id, price in rows}
