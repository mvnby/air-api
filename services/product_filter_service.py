"""Filter-oriented product service operations."""

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from crud.product import ProductDAO
from models import Brand, Product, Tag, TagGroup
from services.tag_logic import is_invalid_brand_name, is_invalid_brand_slug


ALLOWED_FILTER_GROUP_SLUGS = {"brand", "series", "expert-badge", "type", "category"}


class ProductFilterService:
    @staticmethod
    async def resolve_slugs_to_grouped_ids(
        session: AsyncSession,
        slugs: List[str],
    ) -> Dict[int, List[int]]:
        if not slugs:
            return {}

        stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.slug.in_(slugs))
            .where(TagGroup.slug.in_(ALLOWED_FILTER_GROUP_SLUGS))
        )
        tags = (await session.execute(stmt)).scalars().all()

        grouped: Dict[int, List[int]] = {}
        for tag in tags:
            if tag.group_id is None:
                continue
            grouped.setdefault(tag.group_id, []).append(tag.id)
        return grouped

    @staticmethod
    async def get_filters_config(session: AsyncSession) -> Dict[str, Any]:
        price_q = await session.execute(
            select(func.min(Product.price), func.max(Product.price)).where(Product.is_published == True)
        )
        area_q = await session.execute(
            select(
                func.min(ProductDAO.area_expr(session)),
                func.max(ProductDAO.area_expr(session)),
            ).where(Product.is_published == True)
        )
        price_min, price_max = price_q.one()
        area_min, area_max = area_q.one()

        brands_stmt = (
            select(Brand)
            .join(Product, Product.brand_id == Brand.id)
            .where(Brand.is_published == True)
            .where(Product.is_published == True)
            .group_by(Brand.id)
            .order_by(Brand.sort_order, Brand.title)
        )
        expert_stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.is_public == True)
            .where(TagGroup.is_public == True)
            .where((TagGroup.slug == "expert-badge") | (TagGroup.is_expert_badge == True))
            .order_by(Tag.sort_order, Tag.title)
        )

        brands = list((await session.execute(brands_stmt)).scalars().all())
        brands = [
            brand
            for brand in brands
            if not is_invalid_brand_name(brand.title) and not is_invalid_brand_slug(brand.slug)
        ]
        expert_tags = list((await session.execute(expert_stmt)).scalars().all())

        return {
            "price": {"min": price_min, "max": price_max},
            "area": {"min": area_min, "max": area_max},
            "brands": [
                {
                    "id": brand.id,
                    "title": brand.title,
                    "slug": brand.slug,
                    "logo_url": brand.logo_url,
                    "sort_order": brand.sort_order,
                }
                for brand in brands
            ],
            "expert_tags": [{"id": t.id, "title": t.title, "slug": t.slug} for t in expert_tags],
        }
