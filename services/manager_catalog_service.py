from typing import Any, Dict, List, Optional

from schemas import (
    BulkProductIdsRequest,
    BulkRoundRequest,
    ManagerCustomerBranchCreatePayload,
    ManagerCustomerBranchUpdatePayload,
    ManagerCustomerUpdatePayload,
    ProductCreate,
    ProductDuplicatePayload,
    ProductUpdate,
)
from services.customer_service import CustomerService
from services.product_service import ProductService
from services.product_manager_service import ProductManagerService
from sqlalchemy.ext.asyncio import AsyncSession
from models.tenancy import TenantScope


class ManagerCatalogService:
    @staticmethod
    async def get_product(
        session: AsyncSession,
        *,
        product_id: int,
    ) -> Optional[Dict[str, Any]]:
        return await ProductService.get_manager_product(session, product_id)

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
        heating_min: Optional[int],
        has_wifi: Optional[bool],
        has_fresh_air: Optional[bool],
        brand_slugs: Optional[list[str]],
        series_id: Optional[int],
        category_slug: Optional[str],
        category_status: Optional[str],
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
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            brand_slugs=brand_slugs,
            series_id=series_id,
            category_slug=category_slug,
            category_status=category_status,
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
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        return await CustomerService.list_for_manager(
            session=session,
            page=page,
            limit=limit,
            search=search,
            customer_type=customer_type,
            only_with_orders=only_with_orders,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def get_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        return await CustomerService.get_for_manager(
            session=session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: ManagerCustomerUpdatePayload,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        update_data = payload.model_dump(exclude_unset=True)
        return await CustomerService.update_for_manager(
            session=session,
            customer_id=customer_id,
            payload=update_data,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_customer_branches(
        session: AsyncSession,
        *,
        customer_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        return await CustomerService.list_branches_for_manager(
            session=session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def create_customer_branch(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: ManagerCustomerBranchCreatePayload,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        return await CustomerService.create_branch_for_manager(
            session=session,
            customer_id=customer_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_customer_branch(
        session: AsyncSession,
        *,
        customer_id: int,
        branch_id: int,
        payload: ManagerCustomerBranchUpdatePayload,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        return await CustomerService.update_branch_for_manager(
            session=session,
            customer_id=customer_id,
            branch_id=branch_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def delete_customer_branch(
        session: AsyncSession,
        *,
        customer_id: int,
        branch_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[bool]:
        return await CustomerService.delete_branch_for_manager(
            session=session,
            customer_id=customer_id,
            branch_id=branch_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_product(
        session: AsyncSession,
        *,
        product_id: int,
        data: ProductUpdate,
    ) -> Optional[Dict[str, Any]]:
        update_data = data.model_dump(exclude_unset=True)
        tag_ids = update_data.pop("tag_ids", None)
        return await ProductService.update_product(session, product_id, update_data, tag_ids)

    @staticmethod
    async def create_product(
        session: AsyncSession,
        *,
        data: ProductCreate,
    ) -> Dict[str, Any]:
        payload = data.model_dump(exclude_unset=True)
        tag_ids = payload.pop("tag_ids", [])
        return await ProductService.create_product(session, payload, tag_ids)

    @staticmethod
    async def duplicate_product(
        session: AsyncSession,
        *,
        product_id: int,
        data: ProductDuplicatePayload,
    ) -> Optional[Dict[str, Any]]:
        payload = data.model_dump(exclude_unset=True)
        tag_ids = payload.pop("tag_ids", None)
        copy_gallery = bool(payload.pop("copy_gallery", True))
        copy_manuals = bool(payload.pop("copy_manuals", True))
        copy_tags = bool(payload.pop("copy_tags", True))
        make_unpublished = bool(payload.pop("make_unpublished", False))
        return await ProductService.duplicate_product(
            session,
            source_product_id=product_id,
            overrides=payload,
            tag_ids=tag_ids,
            copy_gallery=copy_gallery,
            copy_manuals=copy_manuals,
            copy_tags=copy_tags,
            make_unpublished=make_unpublished,
        )

    @staticmethod
    async def delete_product(
        session: AsyncSession,
        *,
        product_id: int,
    ) -> bool:
        return await ProductService.delete_for_manager(session, product_id)

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
    async def bulk_set_prices_to_rrc(
        session: AsyncSession,
        *,
        request: BulkProductIdsRequest,
    ) -> Dict[str, Any]:
        if not request.product_ids:
            return {
                "message": "No products selected",
                "processed_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
            }
        return await ProductService.bulk_set_prices_to_rrc(session, request.product_ids)

    @staticmethod
    async def bulk_delete_products(
        session: AsyncSession,
        *,
        request: BulkProductIdsRequest,
    ) -> Dict[str, Any]:
        if not request.product_ids:
            return {
                "message": "No products selected",
                "deleted_count": 0,
                "failed_count": 0,
                "errors": [],
            }
        return await ProductService.bulk_delete_for_manager(session, request.product_ids)

    @staticmethod
    async def get_all_tags(session: AsyncSession):
        return await ProductService.get_all_tags(session)

    @staticmethod
    async def smart_search(
        session: AsyncSession,
        *,
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
    ):
        return await ProductManagerService.smart_search(
            session=session,
            q=q,
            limit=limit,
            is_inverter=is_inverter,
            area_min=area_min,
            area_max=area_max,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            brand_slugs=brand_slugs,
            category_slug=category_slug,
        )
