from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND, PRODUCT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    BULK_ROUND_PRICE,
    CATALOG_IMPORT,
    GET_ALL_TAGS,
    GET_MANAGER_CUSTOMERS,
    GET_MANAGER_CUSTOMER_DETAIL,
    GET_MANAGER_CUSTOMER_DOCS,
    GET_MANAGER_CUSTOMER_BRANCHES,
    CREATE_MANAGER_CUSTOMER_BRANCH,
    PATCH_MANAGER_CUSTOMER_BRANCH,
    DELETE_MANAGER_CUSTOMER_BRANCH,
    GET_MANAGER_PRODUCTS,
    PATCH_MANAGER_CUSTOMER,
    DELETE_MANAGER_CUSTOMER,
    SMART_SEARCH_PRODUCTS,
    UPDATE_PRODUCT,
    DELETE_MANAGER_PRODUCT,
    IMPORT_ONLINER,
)
from schemas import (
    BulkRoundRequest,
    CatalogImportPayload,
    CatalogImportResultResponse,
    ManagerActionMessageResponse,
    ManagerCatalogCustomerItemResponse,
    ManagerBulkRoundPriceResponse,
    ManagerCatalogCustomerListResponse,
    ManagerCustomerBranchCreatePayload,
    ManagerCustomerBranchItemResponse,
    ManagerCustomerBranchListResponse,
    ManagerCustomerBranchUpdatePayload,
    ManagerCustomerDocumentListResponse,
    ManagerCatalogProductListResponse,
    ManagerCustomerUpdatePayload,
    ManagerTagGroupResponse,
    OnlinerImportPayload,
    OnlinerImportResultResponse,
    ProductUpdate,
)
from services.manager_catalog_service import ManagerCatalogService
from services.document_service import DocumentService
from services.importer_service import ImporterService

_importer = ImporterService()


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
    category_slug: Optional[str] = Query(None, description="Category tag slug: cat-household/cat-multi/cat-industrial"),
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
        category_slug=category_slug,
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


@router.get(
    "/customers/{customer_id}/branches",
    response_model=ManagerCustomerBranchListResponse,
    operation_id=GET_MANAGER_CUSTOMER_BRANCHES,
)
async def list_customer_branches_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    data = await ManagerCatalogService.list_customer_branches(session=session, customer_id=customer_id)
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_BRANCHES,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/customers/{customer_id}/branches",
    response_model=ManagerCustomerBranchItemResponse,
    operation_id=CREATE_MANAGER_CUSTOMER_BRANCH,
)
async def create_customer_branch_for_manager(
    customer_id: int,
    payload: ManagerCustomerBranchCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        data = await ManagerCatalogService.create_customer_branch(
            session=session,
            customer_id=customer_id,
            payload=payload,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_CUSTOMER_BRANCH,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.patch(
    "/customers/{customer_id}/branches/{branch_id}",
    response_model=ManagerCustomerBranchItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER_BRANCH,
)
async def patch_customer_branch_for_manager(
    customer_id: int,
    branch_id: int,
    payload: ManagerCustomerBranchUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        data = await ManagerCatalogService.update_customer_branch(
            session=session,
            customer_id=customer_id,
            branch_id=branch_id,
            payload=payload,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER_BRANCH,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.delete(
    "/customers/{customer_id}/branches/{branch_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_CUSTOMER_BRANCH,
)
async def delete_customer_branch_for_manager(
    customer_id: int,
    branch_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    data = await ManagerCatalogService.delete_customer_branch(
        session=session,
        customer_id=customer_id,
        branch_id=branch_id,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return {"message": "Branch deleted"}


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


@router.delete(
    "/customers/{customer_id}",
    operation_id=DELETE_MANAGER_CUSTOMER,
)
async def delete_customer_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        from services.customer_service import CustomerService
        success = await CustomerService.delete_for_manager(session, customer_id)
        if not success:
            raise manager_http_error(
                status_code=404,
                endpoint=DELETE_MANAGER_CUSTOMER,
                error_code=CUSTOMER_NOT_FOUND,
            )
        return {"ok": True}
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_CUSTOMER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


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


@router.delete(
    "/products/{product_id}",
    operation_id=DELETE_MANAGER_PRODUCT,
)
async def delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        success = await ManagerCatalogService.delete_product(
            session=session,
            product_id=product_id,
        )
        if not success:
            raise manager_http_error(
                status_code=404,
                endpoint=DELETE_MANAGER_PRODUCT,
                error_code=PRODUCT_NOT_FOUND,
            )
        return {"ok": True}
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_PRODUCT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


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
    is_inverter: Optional[bool] = Query(None),
    has_wifi: Optional[bool] = Query(None),
    category_slug: Optional[str] = Query(None, description="Category tag slug: cat-household/cat-multi/cat-industrial"),
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
        is_inverter=is_inverter,
        has_wifi=has_wifi,
        category_slug=category_slug,
    )


@router.post(
    "/catalog/import-onliner",
    response_model=OnlinerImportResultResponse,
    operation_id=IMPORT_ONLINER,
)
async def import_from_onliner(
    payload: OnlinerImportPayload,
    _user: str = Depends(get_current_username),
):
    """
    Import products from Onliner.by URLs.
    Accepts a list of product page URLs and an optional flag to also import
    related models (sibling AC units linked on the same page).
    Returns the count of successfully imported and failed products.
    """
    urls = [u.strip() for u in payload.urls if u.strip()]
    results = await _importer.import_products_bulk(
        urls,
        with_related=payload.with_related,
        update_existing=payload.update_existing,
    )
    return OnlinerImportResultResponse(
        success_count=len(results["success"]),
        error_count=len(results["errors"]),
        successes=results["success"],
        errors=results["errors"],
    )


@router.post(
    "/catalog/import",
    response_model=CatalogImportResultResponse,
    operation_id=CATALOG_IMPORT,
)
async def catalog_import(
    payload: CatalogImportPayload,
    _user: str = Depends(get_current_username),
):
    """
    Universal product import endpoint.
    Accepts URLs from any supported source (onliner.by, aircond.by, etc.).
    ImporterService automatically routes each URL to the appropriate parser.
    """
    urls = [u.strip() for u in payload.urls if u.strip()]
    results = await _importer.import_products_bulk(
        urls,
        with_related=payload.with_related,
        update_existing=payload.update_existing,
    )
    return CatalogImportResultResponse(
        success_count=len(results["success"]),
        error_count=len(results["errors"]),
        successes=results["success"],
        errors=results["errors"],
    )
