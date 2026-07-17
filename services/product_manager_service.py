"""Manager-facing product service operations."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models.product import Product, Tag
from services.catalog_revision_service import CatalogRevisionService
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
    def _serialize_manuals(product: Product) -> List[Dict[str, Any]]:
        return [
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "url": item.url,
                "source": item.source,
            }
            for item in (product.attachments or [])
            if item.kind == "manual"
        ]

    @staticmethod
    async def smart_search(
        session: AsyncSession,
        q: str,
        limit: int = 40,
        is_inverter: Optional[bool] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        brand_slugs: Optional[List[str]] = None,
        category_slug: Optional[str] = None,
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
                selectinload(Product.gallery_images),
                selectinload(Product.attachments),
            )
            .where(Product.is_published.is_(True))
        )

        stmt = ProductDAO._apply_smart_search_filter(stmt, q)

        stmt = ProductDAO._apply_common_filters(
            session=session,
            stmt=stmt,
            area_min=area_min,
            area_max=area_max,
            heating_min=heating_min,
            is_inverter=is_inverter,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            tag_slugs=[category_slug] if category_slug else None,
            brand_slugs=brand_slugs,
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
                "source_url": p.source_url,
                "specs": sanitize_specs(p.specs),
                "gallery_images": [
                    {
                        "id": img.id,
                        "url": img.url,
                        "is_installation_photo": img.is_installation_photo,
                    }
                    for img in (p.gallery_images or [])
                ],
                "manuals": ProductManagerService._serialize_manuals(p),
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
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        brand_slugs: Optional[List[str]] = None,
        series_id: Optional[int] = None,
        category_slug: Optional[str] = None,
        category_status: Optional[str] = None,
        sort: str = "recommended",
    ) -> Dict[str, Any]:
        items, total = await ProductDAO.get_for_manager(
            session,
            page=page,
            limit=limit,
            search=search,
            is_published=is_published,
            area_min=area_min,
            area_max=area_max,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            brand_slugs=brand_slugs,
            series_id=series_id,
            category_slug=category_slug,
            category_status=category_status,
            sort=sort,
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
                    "manuals": ProductManagerService._serialize_manuals(p),
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
        from models.product import ProductAttachment, ProductImage, ProductTagLink
        from models.supplier import ProductLocalStock, ProductSupplierMapping
        import sqlalchemy as sa
        
        product = await session.get(Product, product_id)
        if not product:
            return False
        product_slug = product.slug
        brand_slugs = await CatalogRevisionService.get_product_brand_slugs(
            session,
            [product_id],
        )
            
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
        await session.execute(
            sa.delete(ProductAttachment).where(ProductAttachment.product_id == product_id)
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
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="product_delete",
            product_ids=[product_id],
            slugs=[product_slug] if product_slug else None,
            brand_slugs=brand_slugs,
        )
        return True

    @staticmethod
    async def bulk_delete_for_manager(session: AsyncSession, product_ids: List[int]) -> Dict[str, Any]:
        deleted_count = 0
        errors: List[Dict[str, Any]] = []

        for product_id in product_ids:
            try:
                deleted = await ProductManagerService.delete_for_manager(session, product_id)
                if deleted:
                    deleted_count += 1
                else:
                    errors.append({"product_id": product_id, "message": "Товар не найден"})
            except ValueError as exc:
                errors.append({"product_id": product_id, "message": str(exc)})
            except Exception as exc:
                await session.rollback()
                errors.append({"product_id": product_id, "message": str(exc)})

        failed_count = len(errors)
        return {
            "message": "Bulk delete completed",
            "deleted_count": deleted_count,
            "failed_count": failed_count,
            "errors": errors,
        }
