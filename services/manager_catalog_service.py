from typing import Any, Dict, Optional

from schemas import BulkRoundRequest, ProductUpdate
from services.customer_service import CustomerService
from services.product_service import ProductService
from sqlalchemy.ext.asyncio import AsyncSession


class ManagerCatalogService:
    @staticmethod
    async def list_products(
        session: AsyncSession,
        *,
        page: int,
        limit: int,
        search: Optional[str],
        is_published: Optional[bool],
        area_min: Optional[int],
        area_max: Optional[int],
        is_inverter: Optional[bool],
        sort: str,
    ) -> Dict[str, Any]:
        return await ProductService.get_manager_list(
            session=session,
            page=page,
            limit=limit,
            search=search,
            is_published=is_published,
            area_min=area_min,
            area_max=area_max,
            is_inverter=is_inverter,
            sort=sort,
        )

    @staticmethod
    async def list_customers(
        session: AsyncSession,
        *,
        page: int,
        limit: int,
        search: Optional[str],
        customer_type: Optional[str],
        only_with_orders: bool,
    ) -> Dict[str, Any]:
        return await CustomerService.list_for_manager(
            session=session,
            page=page,
            limit=limit,
            search=search,
            customer_type=customer_type,
            only_with_orders=only_with_orders,
        )

    @staticmethod
    async def update_product(
        session: AsyncSession,
        *,
        product_id: int,
        data: ProductUpdate,
    ) -> Optional[Dict[str, Any]]:
        update_data = data.dict(exclude_unset=True)
        tag_ids = update_data.pop("tag_ids", None)
        return await ProductService.update_product(session, product_id, update_data, tag_ids)

    @staticmethod
    async def bulk_round_prices(
        session: AsyncSession,
        *,
        request: BulkRoundRequest,
    ) -> Dict[str, Any]:
        if not request.product_ids:
            return {"message": "No products selected", "updated_count": 0}
        return await ProductService.bulk_round_prices(session, request.product_ids)

    @staticmethod
    async def get_all_tags(session: AsyncSession):
        return await ProductService.get_all_tags(session)
