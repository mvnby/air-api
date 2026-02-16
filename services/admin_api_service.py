"""Service-layer helpers for admin/search/health API endpoints."""

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from models import Product, ProductTagLink, Service, Tag, TagGroup


class AdminApiService:
    @staticmethod
    async def get_filterable_tags(session: AsyncSession) -> List[Dict[str, Any]]:
        stmt = (
            select(TagGroup, Tag)
            .join(Tag, Tag.group_id == TagGroup.id)
            .where(Tag.is_filter == True)
            .order_by(TagGroup.sort_order, TagGroup.title, Tag.sort_order, Tag.title)
        )
        result = await session.execute(stmt)

        grouped = {}
        for group, tag in result:
            if group.title not in grouped:
                grouped[group.title] = {
                    "group_label": group.title,
                    "tags": [],
                }
            grouped[group.title]["tags"].append(
                {
                    "id": tag.id,
                    "title": tag.title,
                    "slug": tag.slug,
                }
            )

        return list(grouped.values())

    @staticmethod
    async def search_products(session: AsyncSession, q: str = "", tag_ids: List[int] | None = None) -> List[Dict[str, Any]]:
        stmt = select(Product)

        if tag_ids:
            tag_subquery = (
                select(ProductTagLink.product_id)
                .where(ProductTagLink.tag_id.in_(tag_ids))
                .group_by(ProductTagLink.product_id)
                .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
            )
            stmt = stmt.where(Product.id.in_(tag_subquery))

        if q:
            pattern = f"%{q}%"
            stmt = stmt.where((Product.title.ilike(pattern)) | (Product.description.ilike(pattern)))

        stmt = stmt.limit(20)
        result = await session.execute(stmt)
        products = result.scalars().all()
        return [{"id": p.id, "text": p.title, "price": p.price} for p in products]

    @staticmethod
    async def search_services(session: AsyncSession, q: str = "") -> List[Dict[str, Any]]:
        stmt = select(Service).where(Service.title.ilike(f"%{q}%")).limit(20)
        result = await session.execute(stmt)
        services = result.scalars().all()
        return [{"id": s.id, "text": s.title, "price": s.base_price} for s in services]

    @staticmethod
    async def health_check(session: AsyncSession) -> Dict[str, str]:
        try:
            await session.execute(select(1))
            return {"status": "ok", "database": "online"}
        except Exception as exc:
            return {"status": "error", "database": "offline", "detail": str(exc)}
