"""Manager-facing product service operations."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models.product import Product, Tag
from services.product_serialization import sanitize_specs

# ---------------------------------------------------------------------------
# BTU index → area (m²) and power_cooling (kW) ranges.
# Ranges include a small "dictionary gap" so partial catalogue data still
# matches (e.g. some units use area=0, relying on the title ILIKE fallback).
# ---------------------------------------------------------------------------
from models.product_constants import BTU_MAPPING


class ProductManagerService:
    @staticmethod
    async def smart_search(
        session: AsyncSession,
        q: str,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        """Parse a free-text query and return matching products.

        Parsing rules:
        - Tokens that consist entirely of digits → ``number_tokens`` (BTU index
          candidates or plain numeric text).
        - All other tokens → ``text_tokens`` (brand/series name words).

        Filter construction:
        - Each *text* token must be present in ``title`` OR any related ``Tag.title``
          (AND-chained across tokens).
        - Each *number* token is looked up in ``BTU_MAPPING``:
          - on hit  → filter on area range OR power_cooling range OR title ILIKE
            (covers products where area=0 but BTU is embedded in the name).
          - on miss → plain title ILIKE fallback.
        """
        stmt = (
            select(Product)
            .options(
                selectinload(Product.tags).selectinload(Tag.group),
                selectinload(Product.gallery_images)
            )
            .where(Product.is_published.is_(True))
        )

        stmt = ProductDAO._apply_smart_search_filter(stmt, q)

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        products = result.scalars().all()

        formatted_items = [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "price": p.price,
                "old_price": p.old_price,
                "area": p.area,
                "is_inverter": p.is_inverter,
                "power_cooling": p.power_cooling,
                "main_image": p.main_image,
                "is_published": p.is_published,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "specs": sanitize_specs(p.specs),
                "gallery_images": [
                    {
                        "id": img.id,
                        "url": img.url,
                        "is_installation_photo": img.is_installation_photo,
                    }
                    for img in (p.gallery_images or [])
                ],
                "tags": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "slug": t.slug,
                        "group_title": t.group.title if t.group else None,
                        "group_color": t.group.color if t.group else "secondary",
                    }
                    for t in (p.tags or [])
                ],
            }
            for p in products
        ]

        return {
            "items": formatted_items,
            "meta": {
                "page": 1,
                "limit": limit,
                "total": len(products),
                "pages": 1,
            },
        }

    @staticmethod
    async def get_manager_list(
        session: AsyncSession,
        page: int = 1,
        limit: int = 40,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        sort: str = "newest",
    ) -> Dict[str, Any]:
        items, total = await ProductDAO.get_for_manager(
            session, page, limit, search, is_published, area_min, area_max, is_inverter, sort
        )

        formatted_items = []
        for p in items:
            formatted_items.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "slug": p.slug,
                    "price": p.price,
                    "old_price": p.old_price,
                    "area": p.area,
                    "is_inverter": p.is_inverter,
                    "power_cooling": p.power_cooling,
                    "main_image": p.main_image,
                    "is_published": p.is_published,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "specs": sanitize_specs(p.specs),
                    "gallery_images": [
                        {
                            "id": img.id,
                            "url": img.url,
                            "is_installation_photo": img.is_installation_photo,
                        }
                        for img in (p.gallery_images or [])
                    ],
                    "tags": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "slug": t.slug,
                            "group_title": t.group.title if t.group else None,
                            "group_color": t.group.color if t.group else "secondary",
                        }
                        for t in (p.tags or [])
                    ],
                }
            )

        return {
            "items": formatted_items,
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def get_all_tags(session: AsyncSession) -> List[Dict[str, Any]]:
        from crud.tag import TagDAO

        groups = await TagDAO.get_all_grouped(session)
        return [
            {
                "id": g.id,
                "title": g.title,
                "slug": g.slug,
                "color": g.color,
                "allow_multiple": g.allow_multiple,
                "tags": [
                    {"id": t.id, "title": t.title, "slug": t.slug}
                    for t in sorted(g.tags, key=lambda item: (item.sort_order, item.title))
                ],
            }
            for g in groups
        ]
