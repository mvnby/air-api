"""Locked price snapshots for public checkout."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_
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
    async def get_shared_snapshots_by_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: set[int],
    ) -> dict[int, LockedPublicCatalogProduct]:
        if not product_ids:
            return {}
        rows = (
            await session.execute(
                select(
                    Product.id,
                    Product.title,
                    Product.price,
                    Storefront.currency,
                )
                .select_from(Product)
                .join(
                    Storefront,
                    and_(
                        Storefront.id == tenant_scope.storefront_id,
                        Storefront.tenant_id == tenant_scope.tenant_id,
                    ),
                )
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                    Storefront.status == "active",
                )
                .order_by(Product.id.asc())
                .with_for_update(read=True, of=(Product, Storefront))
            )
        ).all()
        return {
            int(product_id): LockedPublicCatalogProduct(
                product_id=int(product_id),
                title=str(title),
                unit_price=int(price),
                currency=str(currency),
            )
            for product_id, title, price, currency in rows
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
        rows = (
            await session.execute(
                select(
                    Product.id,
                    Product.title,
                    TenantOffer.price,
                    Storefront.currency,
                )
                .select_from(Product)
                .join(TenantOffer, TenantOffer.product_id == Product.id)
                .join(
                    Storefront,
                    and_(
                        Storefront.id == tenant_scope.storefront_id,
                        Storefront.tenant_id == tenant_scope.tenant_id,
                    ),
                )
                .where(
                    Product.id.in_(product_ids),
                    Product.is_published.is_(True),
                    Storefront.status == "active",
                    *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
                )
                .order_by(Product.id.asc())
                .with_for_update(
                    read=True,
                    of=(Product, TenantOffer, Storefront),
                )
            )
        ).all()
        return {
            int(product_id): LockedPublicCatalogProduct(
                product_id=int(product_id),
                title=str(title),
                unit_price=int(price),
                currency=str(currency),
            )
            for product_id, title, price, currency in rows
        }
