"""Manager-facing product service operations."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models.product import Product, Tag
from services.product_serialization import sanitize_specs
from services.product_supply_metrics_service import ProductSupplyMetricsService

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
        is_inverter: Optional[bool] = None,
        has_wifi: Optional[bool] = None,
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

        stmt = ProductDAO._apply_common_filters(
            session=session,
            stmt=stmt,
            is_inverter=is_inverter,
            has_wifi=has_wifi,
            is_published=None,
        )

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        products = result.scalars().all()
        supply_metrics = await ProductSupplyMetricsService.compute_for_products(session, list(products))

        formatted_items = [
            {
                "id": p.id,
                "brand_id": p.brand_id,
                "series_id": p.series_id,
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
                "min_cost_byn": supply_metrics.get(p.id, {}).get("min_cost_byn"),
                "recommended_price_byn": supply_metrics.get(p.id, {}).get("recommended_price_byn"),
                "margin_abs_preview": supply_metrics.get(p.id, {}).get("margin_abs_preview"),
                "margin_pct_preview": supply_metrics.get(p.id, {}).get("margin_pct_preview"),
                "vitebsk_qty": supply_metrics.get(p.id, {}).get("vitebsk_qty", 0),
                "minsk_qty": supply_metrics.get(p.id, {}).get("minsk_qty", 0),
                "availability_status": supply_metrics.get(p.id, {}).get("availability_status", "out_of_stock"),
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
        supply_metrics = await ProductSupplyMetricsService.compute_for_products(session, list(items))

        formatted_items = []
        for p in items:
            formatted_items.append(
                {
                    "id": p.id,
                    "brand_id": p.brand_id,
                    "series_id": p.series_id,
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
                    "min_cost_byn": supply_metrics.get(p.id, {}).get("min_cost_byn"),
                    "recommended_price_byn": supply_metrics.get(p.id, {}).get("recommended_price_byn"),
                    "margin_abs_preview": supply_metrics.get(p.id, {}).get("margin_abs_preview"),
                    "margin_pct_preview": supply_metrics.get(p.id, {}).get("margin_pct_preview"),
                    "vitebsk_qty": supply_metrics.get(p.id, {}).get("vitebsk_qty", 0),
                    "minsk_qty": supply_metrics.get(p.id, {}).get("minsk_qty", 0),
                    "availability_status": supply_metrics.get(p.id, {}).get("availability_status", "out_of_stock"),
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
                "is_public": g.is_public,
                "allow_multiple": g.allow_multiple,
                "tags": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "slug": t.slug,
                        "is_public": t.is_public,
                        "is_filter": t.is_filter,
                    }
                    for t in sorted(g.tags, key=lambda item: (item.sort_order, item.title))
                ],
            }
            for g in groups
        ]

    @staticmethod
    async def delete_for_manager(session: AsyncSession, product_id: int) -> bool:
        from models.order import OrderProductLink
        from models.product import ProductImage, ProductTagLink
        from models.supplier import ProductLocalStock, ProductSupplierMapping
        import sqlalchemy as sa
        
        product = await session.get(Product, product_id)
        if not product:
            return False
            
        # Check if product is used in any orders
        link_check = await session.execute(
            select(OrderProductLink.id).where(OrderProductLink.product_id == product_id).limit(1)
        )
        has_orders = link_check.scalar_one_or_none() is not None
        
        if has_orders:
            raise ValueError("Товар используется в заказах. Снимите его с публикации вместо удаления.")
            
        # Delete gallery images
        await session.execute(
            sa.delete(ProductImage).where(ProductImage.product_id == product_id)
        )
        
        # Delete tag links explicitly to avoid async lazy-load issues on relationship mutation.
        await session.execute(
            sa.delete(ProductTagLink).where(ProductTagLink.product_id == product_id)
        )
        
        # Delete supplier mappings and local stock (both have NOT NULL product_id).
        await session.execute(
            sa.delete(ProductSupplierMapping).where(ProductSupplierMapping.product_id == product_id)
        )
        await session.execute(
            sa.delete(ProductLocalStock).where(ProductLocalStock.product_id == product_id)
        )
        
        await session.delete(product)
        await session.commit()
        return True
