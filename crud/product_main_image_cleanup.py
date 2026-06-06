"""DAO helpers for product main-image cleanup lifecycle."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Product,
    ProductImage,
    ProductMainImageCleanupBatch,
    ProductMainImageCleanupItem,
)


class ProductMainImageCleanupDAO:
    @staticmethod
    async def list_products_with_main_images(session: AsyncSession) -> list[Product]:
        result = await session.execute(
            select(Product)
            .where(Product.main_image.is_not(None))
            .order_by(Product.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_item_by_product_source(
        session: AsyncSession,
        *,
        product_id: int,
        original_image_url: str,
    ) -> ProductMainImageCleanupItem | None:
        result = await session.execute(
            select(ProductMainImageCleanupItem).where(
                ProductMainImageCleanupItem.product_id == product_id,
                ProductMainImageCleanupItem.original_image_url == original_image_url,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_source_product_image(
        session: AsyncSession,
        *,
        product_id: int,
        image_url: str,
    ) -> ProductImage | None:
        result = await session.execute(
            select(ProductImage)
            .where(
                ProductImage.product_id == product_id,
                ProductImage.url == image_url,
            )
            .order_by(ProductImage.id)
        )
        return result.scalars().first()

    @staticmethod
    async def list_batches(
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
    ) -> list[ProductMainImageCleanupBatch]:
        result = await session.execute(
            select(ProductMainImageCleanupBatch)
            .order_by(ProductMainImageCleanupBatch.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_items(
        session: AsyncSession,
        *,
        batch_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductMainImageCleanupItem]:
        stmt = select(ProductMainImageCleanupItem)
        if batch_id is not None:
            stmt = stmt.where(ProductMainImageCleanupItem.batch_id == batch_id)
        if status is not None:
            stmt = stmt.where(ProductMainImageCleanupItem.status == status)
        result = await session.execute(
            stmt.order_by(ProductMainImageCleanupItem.id.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
