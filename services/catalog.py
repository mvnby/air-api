"""Catalog helpers for specific storefront blocks."""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, Tag
from models.supplier import ProductLocalStock


class CatalogService:
    @staticmethod
    async def get_vitebsk_featured_products(
        session: AsyncSession,
        limit: int = 6,
    ) -> List[Product]:
        """
        Featured catalog for the "В наличии в Витебске" home block.

        Returns:
          - published products only
          - only products with `ProductLocalStock.qty > 0` for warehouse `vitebsk`
          - sorted by novelty (`created_at desc`)
        """

        stmt = (
            select(Product)
            .join(ProductLocalStock, Product.id == ProductLocalStock.product_id)
            .options(
                selectinload(Product.tags).selectinload(Tag.group),
                selectinload(Product.gallery_images),
            )
            .where(
                Product.is_published.is_(True),
                ProductLocalStock.warehouse_code == "vitebsk",
                ProductLocalStock.qty > 0,
            )
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

