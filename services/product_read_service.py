"""Read-oriented product service operations (catalog/search/filters)."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from models import Product
from services.product_dict_mapper import map_product_to_dict
from services.product_filter_service import ProductFilterService
from services.product_series_service import ProductSeriesService


class ProductReadService(ProductFilterService, ProductSeriesService):
    @staticmethod
    def validate_public_pagination(page: int, limit: int) -> None:
        if page < 1:
            raise ValueError("Page must be >= 1")
        if limit < 1 or limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")

    @staticmethod
    async def get_public_spec_keys(session: AsyncSession) -> Dict[str, Any]:
        stmt = select(Product.specs)
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
    async def get_catalog_page(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 20,
        sort: str = "newest",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        tag_slugs: Optional[List[str]] = None,
        is_inverter: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        faceted_tag_ids = None
        if tag_slugs:
            faceted_tag_ids = await ProductReadService.resolve_slugs_to_grouped_ids(session, tag_slugs)

        items = await ProductDAO.get_filtered(
            session,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            heating_min=heating_min,
            has_wifi=has_wifi,
            is_inverter=is_inverter,
            tag_slugs=None,
            faceted_tag_ids=faceted_tag_ids,
            sort=sort,
            page=page,
            limit=limit,
            is_published=True,
            search_query=search,
        )
        total = await ProductDAO.count_filtered(
            session,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            heating_min=heating_min,
            has_wifi=has_wifi,
            is_inverter=is_inverter,
            tag_slugs=None,
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
        if is_inverter is not None:
            smart_results = [item for item in smart_results if bool(item.get("is_inverter")) is is_inverter]
        return smart_results[:limit]

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        area: int,
        is_inverter: bool,
        tag_slugs: Optional[List[str]] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        faceted_tag_ids = None
        if tag_slugs:
            faceted_tag_ids = await ProductReadService.resolve_slugs_to_grouped_ids(session, tag_slugs)

        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            min_price=min_price,
            max_price=max_price,
            is_published=True,
            faceted_tag_ids=faceted_tag_ids,
            sort="area_asc",
            limit=limit,
        )
        return [ProductReadService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Dict[str, Any]]:
        product = await ProductDAO.get_by_id(session, product_id)
        if product:
            return ProductReadService._to_dict(product)
        return None

    @staticmethod
    async def get_product_by_identifier(session: AsyncSession, identifier: str) -> Optional[Product]:
        if identifier.isdigit():
            product = await ProductDAO.get_by_id(session, int(identifier))
            if product:
                return product
        return await ProductDAO.get_by_slug(session, identifier)

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
