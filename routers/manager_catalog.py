from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    BULK_ROUND_PRICE,
    GET_ALL_TAGS,
    GET_MANAGER_CUSTOMERS,
    GET_MANAGER_CUSTOMER_DETAIL,
    GET_MANAGER_PRODUCTS,
    UPDATE_PRODUCT,
)
from schemas import (
    BulkRoundRequest,
    ManagerActionMessageResponse,
    ManagerCatalogCustomerItemResponse,
    ManagerBulkRoundPriceResponse,
    ManagerCatalogCustomerListResponse,
    ManagerCatalogProductListResponse,
    ManagerTagGroupResponse,
    ProductUpdate,
)
from services.manager_catalog_service import ManagerCatalogService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get(
    "/products/list",
    response_model=ManagerCatalogProductListResponse,
    operation_id=GET_MANAGER_PRODUCTS,
)
async def list_products_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    area_min: Optional[int] = Query(None),
    area_max: Optional[int] = Query(None),
    is_inverter: Optional[bool] = Query(None),
    sort: str = Query("newest"),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated product list for manager UI.
    Unlike the public catalog, this can show unpublished products.
    """
    return await ManagerCatalogService.list_products(
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


@router.get(
    "/customers",
    response_model=ManagerCatalogCustomerListResponse,
    operation_id=GET_MANAGER_CUSTOMERS,
)
async def list_customers_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None, alias="type"),
    only_with_orders: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated customer list for manager UI.
    Includes order count per customer.
    """
    return await ManagerCatalogService.list_customers(
        session=session,
        page=page,
        limit=limit,
        search=search,
        customer_type=customer_type,
        only_with_orders=only_with_orders,
    )


@router.get(
    "/customers/{customer_id}",
    response_model=ManagerCatalogCustomerItemResponse,
    operation_id=GET_MANAGER_CUSTOMER_DETAIL,
)
async def get_customer_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    customer = await ManagerCatalogService.get_customer(session=session, customer_id=customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.patch(
    "/products/{product_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=UPDATE_PRODUCT,
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Update individual product fields.
    """
    result = await ManagerCatalogService.update_product(
        session=session,
        product_id=product_id,
        data=data,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    return result


@router.post(
    "/products/bulk-round-price",
    response_model=ManagerBulkRoundPriceResponse,
    operation_id=BULK_ROUND_PRICE,
)
async def bulk_round_price(
    request: BulkRoundRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Round prices down to the nearest multiple of 50.
    """
    return await ManagerCatalogService.bulk_round_prices(session=session, request=request)


@router.get(
    "/tags/all",
    response_model=list[ManagerTagGroupResponse],
    operation_id=GET_ALL_TAGS,
)
async def get_all_tags(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Return all tags grouped by TagGroup for the product editor.
    """
    return await ManagerCatalogService.get_all_tags(session)
