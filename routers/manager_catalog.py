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
    Read a paginated shared product list for editing, including unpublished cards unless
    filtered. page starts at 1 and limit is 1–100. Brand/category/series and technical
    filters apply to the master catalog; publication here is not a tenant-offer publication
    flag.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    """
    Create a manual shared product, normalize specs and synchronize category, brand/series,
    tags and manuals. Invalid title, references or publication media returns 400.
    is_published defaults to true; creation is not implicitly a draft. POST has no
    idempotency receipt and retries may create another card.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Create a separate card from a source product with submitted overrides and optional
    gallery/manual/tag copying. Publication is inherited unless overridden or
    make_unpublished is set. Gallery copying reuses media URLs. Missing source returns 404;
    invalid fields/media returns 400. Each successful POST creates a new card.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    Update submitted product fields; submitted specs are normalized and supplied
    tags/manuals replace those relations. Brand/series and category are synchronized
    according to explicit overrides and changed inputs. Missing product returns 404; invalid
    fields/references/media returns 400. Writers lock the product to coordinate with bulk
    apply; no expected_version or client idempotency receipt is accepted.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
    """
    Permanently delete a product and its removable catalog relations. References from orders
    prevent deletion and return 400. Missing product returns 404, including after successful
    deletion. This does not mean unpublishing the product.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    Round each existing selected master-product price down to a multiple of 50 and return
    the changed count. Missing IDs are ignored and an empty selection does nothing.
    Repeating without intervening price changes makes no further changes; this does not edit
    tenant offers.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Set existing selected master-product prices to rounded current supplier-derived
    recommended retail prices. Products without a positive RRC remain unchanged;
    skipped_count also includes prices already equal to RRC. Missing IDs are ignored.
    Repeats recalculate current supply metrics and do not edit tenant offers.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Permanently delete explicitly selected products one at a time and report per-product
    failures. Order-linked products cannot be deleted; missing IDs are failures. Successful
    deletions commit individually, so the batch may partially succeed. Empty selection does
    nothing; repeating the batch reports previously deleted IDs as missing.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Read all tags grouped by TagGroup for the shared product editor. No pagination
    parameters are accepted; this does not restrict groups to the selected tenant.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Search the shared catalog for the product picker by text tokens and BTU-index numeric
    tokens with AND-combined matching against titles, tags, area and cooling power.
    Technical/brand/category filters refine results; limit is 1–100. This does not require
    publication or tenant-offer eligibility.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    """
    Read a shared product editor card with its related catalog data, including unpublished
    products. Missing product returns 404; this is not the tenant storefront projection.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    Synchronously import product URLs using the importer, optionally following related
    models and updating existing cards. Blank URLs are stripped; successes and per-product
    errors are returned separately, so success of the HTTP call does not mean all products
    imported. This writes catalog state and downloads media; repeated calls follow
    update_existing and source matching rather than an idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
    Synchronously import URLs from supported catalog sources, selecting the parser for each
    URL. Optional related-model expansion and update_existing control writes. Blank URLs are
    removed and partial successes/errors are returned. This downloads source content/media
    and mutates cards; it is neither preview nor a background-job response.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
    Persist a new catalog import job and return 202 with its ID/status/stage for polling.
    Blank URLs are removed; no remaining URL returns 400. The shared queue runs jobs in
    order; accepted/queued does not mean import completed. Each POST creates a new job with
    no idempotency receipt; results and partial failures are read from job status.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    """
    Read the shared import queue’s current job: the running/queued job is preferred,
    otherwise the latest recorded job. Returns progress and successes/errors without
    starting work; 404 means no recorded job is available.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Read one persisted shared catalog import job by job_id with progress and results/errors.
    Missing job returns 404; polling only reads state and does not retry failed imports.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    job = await catalog_import_runtime_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Catalog import job not found")
    return CatalogImportJobStatusResponse(**job)
