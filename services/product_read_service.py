"""Read-oriented product service operations (catalog/search/filters)."""

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from models import Brand, Product
from services.product_dict_mapper import map_product_to_dict
from services.product_filter_service import ProductFilterService
from services.product_series_service import ProductSeriesService
from services.product_supply_metrics_service import ProductSupplyMetricsService
from services.spec_registry import get_specs_registry_payload


class ProductReadService(ProductFilterService, ProductSeriesService):
    @staticmethod
    async def get_supply_metrics_map(
        session: AsyncSession,
        products: Iterable[Product],
    ) -> Dict[int, Dict[str, Any]]:
        product_list = list(products)
        if not product_list:
            return {}
        return await ProductSupplyMetricsService.compute_for_products(session, product_list)

    @staticmethod
    def validate_public_pagination(page: int, limit: int) -> None:
        if page < 1:
            raise ValueError("Page must be >= 1")
        if limit < 1 or limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")

    @staticmethod
    async def get_public_spec_keys(session: AsyncSession) -> Dict[str, Any]:
        stmt = select(Product.specs).where(Product.is_published.is_(True))
        result = await session.execute(stmt)
        all_specs = result.scalars().all()

        stats: Dict[str, int] = {}
        for spec_dict in all_specs:
            if not spec_dict:
                continue
            for key in spec_dict.keys():
                if str(key).startswith("__"):
                    continue
                stats[key] = stats.get(key, 0) + 1

        return {"keys": sorted(stats.keys()), "total_products_using": stats}

    @staticmethod
    def get_specs_registry() -> Dict[str, Any]:
        return get_specs_registry_payload()

    @staticmethod
    async def get_catalog_page(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 20,
        sort: str = "recommended",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        indoor_types: Optional[List[str]] = None,
        tag_slugs: Optional[List[str]] = None,
        brand_slugs: Optional[List[str]] = None,
        is_inverter: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        faceted_tag_ids = None
        resolved_brand_slugs = list(brand_slugs or [])
        facet_slugs = tag_slugs or []
        if tag_slugs:
            brand_rows = (
                await session.execute(select(Brand.slug).where(Brand.slug.in_(tag_slugs)))
            ).scalars().all()
            legacy_brand_slugs = [slug for slug in brand_rows if slug]
            resolved_brand_slugs.extend(legacy_brand_slugs)
            brand_slug_set = set(legacy_brand_slugs)
            facet_slugs = [slug for slug in tag_slugs if slug not in brand_slug_set]
            faceted_tag_ids = await ProductReadService.resolve_slugs_to_grouped_ids(session, facet_slugs)
        resolved_brand_slugs = list(dict.fromkeys(resolved_brand_slugs))

        items = await ProductDAO.get_filtered(
            session,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            indoor_types=indoor_types,
            is_inverter=is_inverter,
            tag_slugs=None,
            brand_slugs=resolved_brand_slugs,
            faceted_tag_ids=faceted_tag_ids,
            sort=sort,
            page=page,
            limit=limit,
            is_published=True,
            search_query=search,
            load_image_variants=True,
        )
        total = await ProductDAO.count_filtered(
            session,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            indoor_types=indoor_types,
            is_inverter=is_inverter,
            tag_slugs=None,
            brand_slugs=resolved_brand_slugs,
            faceted_tag_ids=faceted_tag_ids,
            is_published=True,
            search_query=search,
        )

        pages = (total + limit - 1) // limit if limit > 0 else 0
        return {
            "items": items,
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages,
            },
        }

    @staticmethod
    async def search(
        session: AsyncSession,
        query: Optional[str] = None,
        is_inverter: Optional[bool] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        from services.product_manager_service import ProductManagerService

        smart_results = await ProductManagerService.smart_search(
            session=session,
            q=(query or "").strip(),
            limit=max(limit, 1),
        )
        smart_items = smart_results.get("items", []) if isinstance(smart_results, dict) else list(smart_results or [])
        if is_inverter is not None:
            smart_items = [item for item in smart_items if bool(item.get("is_inverter")) is is_inverter]
        return smart_items[:limit]

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        area: Optional[int],
        is_inverter: bool,
        tag_slugs: Optional[List[str]] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        faceted_tag_ids = None
        if tag_slugs:
            faceted_tag_ids = await ProductReadService.resolve_slugs_to_grouped_ids(session, tag_slugs)

        products = await ProductDAO.get_filtered(
            session,
            area_min=area_min if area_min is not None else area,
            area_max=area_max,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            min_price=min_price,
            max_price=max_price,
            is_published=True,
            faceted_tag_ids=faceted_tag_ids,
            sort="area_asc",
            limit=limit,
        )
        supply_metrics = await ProductSupplyMetricsService.compute_for_products(session, list(products))

        items = [ProductReadService._to_dict(p) for p in products]
        for item in items:
            pid = item.get("id")
            metrics = supply_metrics.get(pid, {})
            item["vitebsk_qty"] = metrics.get("vitebsk_qty", 0)
            item["minsk_qty"] = metrics.get("minsk_qty", 0)
            item["availability_status"] = metrics.get("availability_status", "out_of_stock")
        return items

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Dict[str, Any]]:
        product = await ProductDAO.get_by_id(session, product_id)
        if product:
            item = ProductReadService._to_dict(product)
            supply_metrics = await ProductSupplyMetricsService.compute_for_products(session, [product])
            metrics = supply_metrics.get(product.id, {})
            item["vitebsk_qty"] = metrics.get("vitebsk_qty", 0)
            item["minsk_qty"] = metrics.get("minsk_qty", 0)
            item["availability_status"] = metrics.get("availability_status", "out_of_stock")
            return item
        return None

    @staticmethod
    async def get_product_by_identifier(session: AsyncSession, identifier: str) -> Optional[Product]:
        if identifier.isdigit():
            product = await ProductDAO.get_by_id(
                session,
                int(identifier),
                load_image_variants=True,
            )
            if product:
                return product
        return await ProductDAO.get_by_slug(
            session,
            identifier,
            load_image_variants=True,
        )

    @staticmethod
    async def get_public_product_by_identifier(session: AsyncSession, identifier: str) -> Optional[Product]:
        if identifier.isdigit():
            product = await ProductDAO.get_by_id(
                session,
                int(identifier),
                is_published=True,
                load_image_variants=True,
            )
            if product:
                return product
        return await ProductDAO.get_by_slug(
            session,
            identifier,
            is_published=True,
            load_image_variants=True,
        )

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Dict[str, Any]]:
        products = await ProductDAO.get_all_published(session)
        return [ProductReadService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_area(session: AsyncSession, area: int, range_offset: int = 10) -> List[Dict[str, Any]]:
        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            area_max=area + range_offset,
            is_published=True,
        )
        return [ProductReadService._to_dict(p) for p in products]

    @staticmethod
    def _to_dict(product: Product) -> Dict[str, Any]:
        return map_product_to_dict(
            product,
            include_tag_groups=True,
            include_media=True,
            sanitize_specs_payload=True,
        )
