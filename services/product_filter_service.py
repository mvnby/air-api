"""Filter-oriented product service operations."""

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from models import Product, Tag, TagGroup


ALLOWED_FILTER_GROUP_SLUGS = {"brand", "series", "expert-badge"}


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
            select(func.min(Product.area), func.max(Product.area)).where(Product.is_published == True)
        )
        price_min, price_max = price_q.one()
        area_min, area_max = area_q.one()

        brands_stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.is_public == True)
            .where(TagGroup.slug == "brand")
            .order_by(Tag.sort_order, Tag.title)
        )
        expert_stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.is_public == True)
            .where((TagGroup.slug == "expert-badge") | (TagGroup.is_expert_badge == True))
            .order_by(Tag.sort_order, Tag.title)
        )

        brands = list((await session.execute(brands_stmt)).scalars().all())
        expert_tags = list((await session.execute(expert_stmt)).scalars().all())

        return {
            "price": {"min": price_min, "max": price_max},
            "area": {"min": area_min, "max": area_max},
            "brands": [{"id": t.id, "title": t.title, "slug": t.slug} for t in brands],
            "expert_tags": [{"id": t.id, "title": t.title, "slug": t.slug} for t in expert_tags],
        }
