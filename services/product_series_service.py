"""Series/siblings product service operations."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ProductTagLink, Tag


class ProductSeriesService:
    @staticmethod
    async def get_series_siblings(
        session: AsyncSession,
        product: Product,
        limit: int = 8,
    ) -> List[Product]:
        series_tag_ids = [
            tag.id
            for tag in (product.tags or [])
            if tag.group and tag.group.slug == "series"
        ]
        if not series_tag_ids:
            return []

        brand_tag_ids = {
            tag.id
            for tag in (product.tags or [])
            if tag.group and tag.group.slug == "brand"
        }

        series_product_ids = (
            select(ProductTagLink.product_id)
            .where(ProductTagLink.tag_id.in_(series_tag_ids))
            .distinct()
            .subquery()
        )

        stmt = (
            select(Product)
            .join(series_product_ids, Product.id == series_product_ids.c.product_id)
            .where(Product.id != product.id)
            .where(Product.is_published == True)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        candidates = list((await session.execute(stmt)).scalars().all())

        def score(item: Product) -> tuple[int, int]:
            item_brand_ids = {
                tag.id for tag in (item.tags or [])
                if tag.group and tag.group.slug == "brand"
            }
            same_brand = 0 if (brand_tag_ids and item_brand_ids.intersection(brand_tag_ids)) else 1
            return (same_brand, item.price or 0)

        candidates.sort(key=score)
        return candidates[:limit]
