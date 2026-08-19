from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from models import Product, TenantOffer
from models.tenancy import TenantScope
from services.public_catalog_visibility_service import (
    PublicCatalogVisibilityService,
    PublicProductProjection,
)


class ProductCollectionCatalogAccess:
    """Fail-closed product projection used by collection reads and writes."""

    @staticmethod
    async def is_canonical(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> bool:
        return await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        )

    @classmethod
    async def visible_by_ids(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: list[int] | set[int] | tuple[int, ...],
    ) -> dict[int, PublicProductProjection]:
        ids = tuple(sorted({int(value) for value in product_ids}))
        if not ids:
            return {}
        if await cls.is_canonical(session, tenant_scope=tenant_scope):
            products = await ProductDAO.get_by_ids(session, list(ids))
            projections = [
                PublicCatalogVisibilityService.project_product(product)
                for product in products
            ]
        else:
            rows = await PublicCatalogDAO.get_by_ids(
                session,
                tenant_scope=tenant_scope,
                product_ids=list(ids),
                require_catalog_grant=True,
            )
            projections = [
                PublicCatalogVisibilityService.project_row(row)
                for row in rows
            ]
        return {
            int(projection.product.id): projection
            for projection in projections
        }

    @classmethod
    async def visible_product_ids(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> set[int]:
        if await cls.is_canonical(session, tenant_scope=tenant_scope):
            statement = select(Product.id).where(Product.is_published.is_(True))
        else:
            statement = (
                select(Product.id)
                .join(TenantOffer, TenantOffer.product_id == Product.id)
                .where(
                    Product.is_published.is_(True),
                    *PublicCatalogDAO.visible_offer_conditions(
                        tenant_scope,
                        require_catalog_grant=True,
                    ),
                )
            )
        return {
            int(value)
            for value in (await session.execute(statement)).scalars().all()
        }

    @classmethod
    async def search_visible(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        search: str,
        limit: int,
    ) -> list[PublicProductProjection]:
        if await cls.is_canonical(session, tenant_scope=tenant_scope):
            products = await ProductDAO.get_filtered(
                session,
                is_published=True,
                search_query=search,
                limit=limit,
            )
            return [
                PublicCatalogVisibilityService.project_product(product)
                for product in products
            ]
        rows = await PublicCatalogDAO.get_filtered(
            session,
            tenant_scope=tenant_scope,
            search_query=search,
            limit=limit,
            require_catalog_grant=True,
        )
        return [
            PublicCatalogVisibilityService.project_row(row)
            for row in rows
        ]


__all__ = ["ProductCollectionCatalogAccess"]
