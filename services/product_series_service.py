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
        stmt = select(Product).where(Product.id != product.id).where(Product.is_published == True)

        if product.series_id:
            stmt = stmt.where(Product.series_id == product.series_id)
        else:
            series_tag_ids = [
                tag.id
                for tag in (product.tags or [])
                if tag.group and tag.group.slug == "series"
            ]
            if not series_tag_ids:
                return []

            series_product_ids = (
                select(ProductTagLink.product_id)
                .where(ProductTagLink.tag_id.in_(series_tag_ids))
                .distinct()
                .subquery()
            )
            stmt = stmt.join(series_product_ids, Product.id == series_product_ids.c.product_id)

        stmt = stmt.options(selectinload(Product.tags).selectinload(Tag.group))
        candidates = list((await session.execute(stmt)).scalars().all())

        def score(item: Product) -> tuple[int, int]:
            same_brand = 1
            if product.brand_id and item.brand_id:
                same_brand = 0 if product.brand_id == item.brand_id else 1
            else:
                product_brand_ids = {
                    tag.id for tag in (product.tags or [])
                    if tag.group and tag.group.slug == "brand"
                }
                item_brand_ids = {
                    tag.id for tag in (item.tags or [])
                    if tag.group and tag.group.slug == "brand"
                }
                same_brand = 0 if (product_brand_ids and item_brand_ids.intersection(product_brand_ids)) else 1
            return (same_brand, item.price or 0)

        candidates.sort(key=score)
        return candidates[:limit]
