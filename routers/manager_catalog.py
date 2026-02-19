from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND, PRODUCT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    BULK_ROUND_PRICE,
    GET_ALL_TAGS,
    GET_MANAGER_CUSTOMERS,
    GET_MANAGER_CUSTOMER_DETAIL,
    GET_MANAGER_CUSTOMER_DOCS,
    GET_MANAGER_PRODUCTS,
    PATCH_MANAGER_CUSTOMER,
    SMART_SEARCH_PRODUCTS,
    UPDATE_PRODUCT,
)
from schemas import (
    BulkRoundRequest,
    ManagerActionMessageResponse,
    ManagerCatalogCustomerItemResponse,
    ManagerBulkRoundPriceResponse,
    ManagerCatalogCustomerListResponse,
    ManagerCustomerDocumentListResponse,
    ManagerCatalogProductListResponse,
    ManagerCustomerUpdatePayload,
    ManagerTagGroupResponse,
    ProductUpdate,
)
from services.manager_catalog_service import ManagerCatalogService
from services.document_service import DocumentService


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
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_DETAIL,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return customer


@router.get(
    "/customers/{customer_id}/docs",
    response_model=ManagerCustomerDocumentListResponse,
    operation_id=GET_MANAGER_CUSTOMER_DOCS,
)
async def get_customer_docs_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    docs = await DocumentService.get_customer_documents(session, customer_id)
    return {
        "items": [
            {
                "id": doc.id,
                "order_id": doc.order_id,
                "doc_type": doc.doc_type,
                "number": doc.number,
                "date": doc.date,
                "edit_url": doc.google_edit_url,
            }
            for doc in docs
        ]
    }


@router.patch(
    "/customers/{customer_id}",
    response_model=ManagerCatalogCustomerItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER,
)
async def patch_customer_for_manager(
    customer_id: int,
    payload: ManagerCustomerUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        customer = await ManagerCatalogService.update_customer(
            session=session,
            customer_id=customer_id,
            payload=payload,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not customer:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER,
            error_code=CUSTOMER_NOT_FOUND,
        )
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
        raise manager_http_error(
            status_code=404,
            endpoint=UPDATE_PRODUCT,
            error_code=PRODUCT_NOT_FOUND,
        )

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


@router.get(
    "/products/smart-search",
    response_model=ManagerCatalogProductListResponse,
    operation_id=SMART_SEARCH_PRODUCTS,
)
async def smart_search_products(
    q: str = Query(..., min_length=1, description="Free-text search query, e.g. 'mdv loft 18'"),
    limit: int = Query(40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Smart search for manager product picker.

    Parses the query string into text tokens and BTU-index number tokens,
    then applies AND-chained ORM filters against title, tags, area, and
    power_cooling.  Returns matched products with their tags pre-loaded.
    """
    return await ManagerCatalogService.smart_search(
        session=session,
        q=q,
        limit=limit,
    )
