from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, PRODUCT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    BULK_ROUND_PRICE,
    BULK_SET_RRC_PRICE,
    BULK_DELETE_MANAGER_PRODUCTS,
    CATALOG_IMPORT,
    GET_CATALOG_IMPORT_JOB_STATUS,
    GET_CURRENT_CATALOG_IMPORT_JOB_STATUS,
    GET_ALL_TAGS,
    GET_MANAGER_PRODUCTS,
    GET_MANAGER_PRODUCT,
    CREATE_MANAGER_PRODUCT,
    DUPLICATE_MANAGER_PRODUCT,
    SMART_SEARCH_PRODUCTS,
    UPDATE_PRODUCT,
    DELETE_MANAGER_PRODUCT,
    IMPORT_ONLINER,
    START_CATALOG_IMPORT_JOB,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    BulkRoundRequest,
    BulkProductIdsRequest,
    CatalogImportPayload,
    CatalogImportJobStartResponse,
    CatalogImportJobStatusResponse,
    CatalogImportResultResponse,
    ManagerActionMessageResponse,
    ManagerBulkRoundPriceResponse,
    ManagerBulkSetRrcPriceResponse,
    ManagerBulkDeleteProductsResponse,
    ManagerCatalogProductListResponse,
    ManagerCatalogProductItemResponse,
    ManagerTagGroupResponse,
    OnlinerImportPayload,
    OnlinerImportResultResponse,
    ProductCreate,
    ProductDuplicatePayload,
    ProductUpdate,
)
from services.catalog_import_runtime_service import catalog_import_runtime_service
from services.manager_catalog_service import ManagerCatalogService
from services.importer_service import ImporterService
from routers import manager_customers

_importer = ImporterService()


router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


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
    heating_min: Optional[int] = Query(None),
    has_wifi: Optional[bool] = Query(None),
    has_fresh_air: Optional[bool] = Query(None),
    brand_slugs: Optional[List[str]] = Query(None, description="Brand slugs to include"),
    series_id: Optional[int] = Query(None, ge=1, description="Exact product series ID"),
    category_slug: Optional[str] = Query(None, description="Category tag slug: cat-household/cat-multi/cat-industrial"),
    category_status: Optional[Literal["assigned", "missing"]] = Query(None, description="Catalog category status: assigned/missing"),
    sort: str = Query("recommended"),
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
        heating_min=heating_min,
        has_wifi=has_wifi,
        has_fresh_air=has_fresh_air,
        brand_slugs=brand_slugs,
        series_id=series_id,
        category_slug=category_slug,
        category_status=category_status,
        sort=sort,
    )


router.include_router(manager_customers.router)


@router.post(
    "/products",
    response_model=ManagerActionMessageResponse,
    operation_id=CREATE_MANAGER_PRODUCT,
)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """Create a manual product card from the manager UI."""
    try:
        return await ManagerCatalogService.create_product(
            session=session,
            data=data,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_PRODUCT,
            error_code=BAD_REQUEST,
            message=str(exc),
            field_errors=getattr(exc, "field_errors", None),
        ) from exc


@router.post(
    "/products/{product_id}/duplicate",
    response_model=ManagerActionMessageResponse,
    operation_id=DUPLICATE_MANAGER_PRODUCT,
)
async def duplicate_product(
    product_id: int,
    data: ProductDuplicatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """Duplicate a product card, optionally overriding selected fields."""
    try:
        result = await ManagerCatalogService.duplicate_product(
            session=session,
            product_id=product_id,
            data=data,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DUPLICATE_MANAGER_PRODUCT,
            error_code=BAD_REQUEST,
            message=str(exc),
            field_errors=getattr(exc, "field_errors", None),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=DUPLICATE_MANAGER_PRODUCT,
            error_code=PRODUCT_NOT_FOUND,
        )
    return result


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
    try:
        result = await ManagerCatalogService.update_product(
            session=session,
            product_id=product_id,
            data=data,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=UPDATE_PRODUCT,
            error_code=BAD_REQUEST,
            message=str(exc),
            field_errors=getattr(exc, "field_errors", None),
        ) from exc

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


@router.post(
    "/products/bulk-set-rrc-price",
    response_model=ManagerBulkSetRrcPriceResponse,
    operation_id=BULK_SET_RRC_PRICE,
)
async def bulk_set_rrc_price(
    request: BulkProductIdsRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Set selected product prices to their current recommended retail prices.
    Products without RRC stay unchanged.
    """
    return await ManagerCatalogService.bulk_set_prices_to_rrc(session=session, request=request)


@router.post(
    "/products/bulk-delete",
    response_model=ManagerBulkDeleteProductsResponse,
    operation_id=BULK_DELETE_MANAGER_PRODUCTS,
)
async def bulk_delete_products(
    request: BulkProductIdsRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Delete explicitly selected products. Products linked to orders are reported as failed.
    """
    return await ManagerCatalogService.bulk_delete_products(session=session, request=request)


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
    area_min: Optional[int] = Query(None),
    area_max: Optional[int] = Query(None),
    heating_min: Optional[int] = Query(None),
    has_wifi: Optional[bool] = Query(None),
    has_fresh_air: Optional[bool] = Query(None),
    brand_slugs: Optional[List[str]] = Query(None, description="Brand slugs to include"),
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
        area_min=area_min,
        area_max=area_max,
        heating_min=heating_min,
        has_wifi=has_wifi,
        has_fresh_air=has_fresh_air,
        brand_slugs=brand_slugs,
        category_slug=category_slug,
    )


@router.get(
    "/products/{product_id}",
    response_model=ManagerCatalogProductItemResponse,
    operation_id=GET_MANAGER_PRODUCT,
)
async def get_product_for_manager(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    product = await ManagerCatalogService.get_product(
        session=session,
        product_id=product_id,
    )
    if not product:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_PRODUCT,
            error_code=PRODUCT_NOT_FOUND,
        )
    return product


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


@router.post(
    "/catalog/import/jobs",
    response_model=CatalogImportJobStartResponse,
    operation_id=START_CATALOG_IMPORT_JOB,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_catalog_import_job(
    payload: CatalogImportPayload,
    _user: str = Depends(get_current_username),
):
    """
    Start a universal catalog import in the background and return a job id
    that can be polled for progress.
    """
    urls = [u.strip() for u in payload.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    job = await catalog_import_runtime_service.start_import(
        urls=urls,
        with_related=payload.with_related,
        update_existing=payload.update_existing,
    )

    return CatalogImportJobStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job["stage"],
    )


@router.get(
    "/catalog/import/jobs/current",
    response_model=CatalogImportJobStatusResponse,
    operation_id=GET_CURRENT_CATALOG_IMPORT_JOB_STATUS,
)
async def get_current_catalog_import_job_status(
    _user: str = Depends(get_current_username),
):
    job = await catalog_import_runtime_service.get_current_job()
    if not job:
        raise HTTPException(status_code=404, detail="Catalog import job not found")
    return CatalogImportJobStatusResponse(**job)


@router.get(
    "/catalog/import/jobs/{job_id}",
    response_model=CatalogImportJobStatusResponse,
    operation_id=GET_CATALOG_IMPORT_JOB_STATUS,
)
async def get_catalog_import_job_status(
    job_id: str,
    _user: str = Depends(get_current_username),
):
    job = await catalog_import_runtime_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Catalog import job not found")
    return CatalogImportJobStatusResponse(**job)
