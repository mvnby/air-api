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
BTU_MAPPING: Dict[str, Dict[str, tuple]] = {
    "7":  {"area": (15, 24),   "power": (2.0, 2.4)},
    "07": {"area": (15, 24),   "power": (2.0, 2.4)},
    "9":  {"area": (25, 32),   "power": (2.5, 3.0)},
    "09": {"area": (25, 32),   "power": (2.5, 3.0)},
    "12": {"area": (33, 42),   "power": (3.2, 4.0)},
    "18": {"area": (45, 60),   "power": (5.0, 5.8)},
    "24": {"area": (65, 80),   "power": (6.5, 8.0)},
    "36": {"area": (90, 110),  "power": (9.5, 11.0)},
}


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
        from sqlalchemy import or_

        tokens = q.strip().split()
        text_tokens = [t for t in tokens if not t.isdigit()]
        number_tokens = [t for t in tokens if t.isdigit()]

        stmt = (
            select(Product)
            .options(
                selectinload(Product.tags).selectinload(Tag.group),
                selectinload(Product.gallery_images)
            )
            .where(Product.is_published.is_(True))
        )

        for word in text_tokens:
            word_filter = or_(
                Product.title.ilike(f"%{word}%"),
                Product.tags.any(Tag.title.ilike(f"%{word}%")),
            )
            stmt = stmt.where(word_filter)

        for num in number_tokens:
            if num in BTU_MAPPING:
                ranges = BTU_MAPPING[num]
                num_filter = or_(
                    Product.area.between(ranges["area"][0], ranges["area"][1]),
                    Product.power_cooling.between(ranges["power"][0], ranges["power"][1]),
                    Product.title.ilike(f"%{num}%"),
                )
            else:
                # Non-standard number (e.g. "2024") → plain text search
                num_filter = Product.title.ilike(f"%{num}%")
            stmt = stmt.where(num_filter)

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
