from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, PRODUCT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    ANALYZE_SUPPLIER_SOURCE,
    BULK_CREATE_SUPPLIER_MAPPINGS,
    CREATE_SUPPLIER,
    CREATE_SUPPLIER_MAPPING,
    CREATE_SUPPLIER_SOURCE,
    DELETE_SUPPLIER,
    DELETE_SUPPLIER_SOURCE,
    DELETE_SUPPLIER_MAPPING,
    GET_PRODUCT_SUPPLIER_OFFERS,
    LIST_SUPPLIER_SOURCE_URL_IMPORT_CANDIDATES,
    LIST_SUPPLIER_SHEETS,
    LIST_SUPPLIERS,
    LIST_SUPPLIER_SOURCES,
    START_SUPPLIER_SOURCE_URL_IMPORT,
    SUGGEST_SUPPLIER_OFFERS,
    SYNC_ALL_SUPPLIER_SOURCES,
    LIST_UNMAPPED_SUPPLIER_OFFERS,
    PATCH_SUPPLIER,
    PATCH_SUPPLIER_SOURCE,
    SYNC_SUPPLIER_SOURCE,
    UPSERT_PRODUCT_LOCAL_STOCK,
)
from schemas import (
    ManagerActionMessageResponse,
    CatalogImportJobStartResponse,
    ProductLocalStockPayload,
    ProductLocalStockResponse,
    SupplierCreatePayload,
    SupplierListResponse,
    SupplierMappingCreatePayload,
    SupplierMappingBulkCreatePayload,
    SupplierMappingBulkCreateResponse,
    SupplierMappingResponse,
    SupplierOfferListResponse,
    SupplierOfferSuggestionsPayload,
    SupplierOfferSuggestionsResponse,
    SupplierSourceUrlImportCandidateListResponse,
    SupplierSourceUrlImportPayload,
    SupplierSourceAnalysisResponse,
    SupplierPriceSourceCreatePayload,
    SupplierPriceSourceListResponse,
    SupplierPriceSourceResponse,
    SupplierPriceSourceUpdatePayload,
    SupplierResponse,
    SupplierSheetTabListResponse,
    SupplierSyncRunResponse,
    SupplierUpdatePayload,
)
from services.catalog_import_runtime_service import catalog_import_runtime_service
from services.supplier_mapping_service import SupplierCatalogService, SupplierMappingService
from services.supplier_sync_service import SupplierSyncService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/suppliers", response_model=SupplierListResponse, operation_id=LIST_SUPPLIERS)
async def list_suppliers(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierCatalogService.list_suppliers(session)


@router.post("/suppliers", response_model=SupplierResponse, operation_id=CREATE_SUPPLIER)
async def create_supplier(
    payload: SupplierCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierCatalogService.create_supplier(session, payload.model_dump())
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLIER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse, operation_id=PATCH_SUPPLIER)
async def patch_supplier(
    supplier_id: int,
    payload: SupplierUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        result = await SupplierCatalogService.update_supplier(
            session, supplier_id, payload.model_dump(exclude_unset=True)
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLIER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_SUPPLIER,
            error_code=BAD_REQUEST,
            message="Supplier not found",
        )
    return result


@router.delete(
    "/suppliers/{supplier_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_SUPPLIER,
)
async def delete_supplier(
    supplier_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    ok = await SupplierCatalogService.delete_supplier(session, supplier_id)
    if not ok:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_SUPPLIER,
            error_code=BAD_REQUEST,
            message="Supplier not found",
        )
    return {"message": "Поставщик удалён"}


@router.get("/suppliers/{supplier_id}/sheets", response_model=SupplierSheetTabListResponse, operation_id=LIST_SUPPLIER_SHEETS)
async def list_supplier_sheets(
    supplier_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        items = await SupplierCatalogService.list_supplier_sheets(session, supplier_id)
        return {"items": items}
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_SUPPLIER_SHEETS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_SUPPLIER_SHEETS,
            error_code=BAD_REQUEST,
            message=f"Failed to load sheets: {exc}",
        ) from exc


@router.get("/supplier-sources", response_model=SupplierPriceSourceListResponse, operation_id=LIST_SUPPLIER_SOURCES)
async def list_supplier_sources(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierCatalogService.list_sources(session)


@router.post("/supplier-sources", response_model=SupplierPriceSourceResponse, operation_id=CREATE_SUPPLIER_SOURCE)
async def create_supplier_source(
    payload: SupplierPriceSourceCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierCatalogService.create_source(session, payload.model_dump())
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/supplier-sources/{source_id}",
    response_model=SupplierPriceSourceResponse,
    operation_id=PATCH_SUPPLIER_SOURCE,
)
async def patch_supplier_source(
    source_id: int,
    payload: SupplierPriceSourceUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        result = await SupplierCatalogService.update_source(
            session, source_id, payload.model_dump(exclude_unset=True)
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message="Source not found",
        )
    return result


@router.delete(
    "/supplier-sources/{source_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_SUPPLIER_SOURCE,
)
async def delete_supplier_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    ok = await SupplierCatalogService.delete_source(session, source_id)
    if not ok:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message="Source not found",
        )
    return {"message": "Источник удалён"}


@router.get(
    "/supplier-sources/{source_id}/analysis",
    response_model=SupplierSourceAnalysisResponse,
    operation_id=ANALYZE_SUPPLIER_SOURCE,
)
async def analyze_supplier_source(
    source_id: int,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierCatalogService.analyze_source(session, source_id, limit=limit)
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=ANALYZE_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ANALYZE_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supplier-sources/{source_id}/sync",
    response_model=SupplierSyncRunResponse,
    operation_id=SYNC_SUPPLIER_SOURCE,
)
async def sync_supplier_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierSyncService.sync_source_by_id(session, source_id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=SYNC_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=SYNC_SUPPLIER_SOURCE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supplier-sources/sync-all",
    response_model=list[SupplierSyncRunResponse],
    operation_id=SYNC_ALL_SUPPLIER_SOURCES,
)
async def sync_all_supplier_sources(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierSyncService.sync_all_active_sources(session)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=SYNC_ALL_SUPPLIER_SOURCES,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/supplier-offers/unmapped",
    response_model=SupplierOfferListResponse,
    operation_id=LIST_UNMAPPED_SUPPLIER_OFFERS,
)
async def list_unmapped_supplier_offers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    supplier_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierMappingService.list_unmapped(
        session=session,
        supplier_id=supplier_id,
        source_id=source_id,
        page=page,
        limit=limit,
    )


@router.get(
    "/supplier-offers/source-url-import-candidates",
    response_model=SupplierSourceUrlImportCandidateListResponse,
    operation_id=LIST_SUPPLIER_SOURCE_URL_IMPORT_CANDIDATES,
)
async def list_supplier_source_url_import_candidates(
    limit: int = Query(100, ge=1, le=200),
    supplier_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierMappingService.list_source_url_import_candidates(
        session=session,
        supplier_id=supplier_id,
        source_id=source_id,
        limit=limit,
    )


@router.post(
    "/supplier-offers/source-url-import",
    response_model=CatalogImportJobStartResponse,
    operation_id=START_SUPPLIER_SOURCE_URL_IMPORT,
)
async def start_supplier_source_url_import(
    payload: SupplierSourceUrlImportPayload,
    _user: str = Depends(get_current_username),
):
    urls = [url.strip() for url in payload.urls if url.strip()]
    if not urls:
        raise manager_http_error(
            status_code=400,
            endpoint=START_SUPPLIER_SOURCE_URL_IMPORT,
            error_code=BAD_REQUEST,
            message="No URLs provided",
        )
    job = await catalog_import_runtime_service.start_import(
        urls=list(dict.fromkeys(urls)),
        with_related=payload.with_related,
        update_existing=payload.update_existing,
    )
    return CatalogImportJobStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job["stage"],
    )


@router.post(
    "/supplier-offers/suggestions",
    response_model=SupplierOfferSuggestionsResponse,
    operation_id=SUGGEST_SUPPLIER_OFFERS,
)
async def suggest_supplier_offers(
    payload: SupplierOfferSuggestionsPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierMappingService.suggest_for_offers(
        session=session,
        items=[i.model_dump() for i in payload.items],
        limit_per_offer=payload.limit_per_offer,
    )


@router.post(
    "/supplier-mappings",
    response_model=SupplierMappingResponse,
    operation_id=CREATE_SUPPLIER_MAPPING,
)
async def create_supplier_mapping(
    payload: SupplierMappingCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    try:
        return await SupplierMappingService.create_mapping(
            session=session,
            product_id=payload.product_id,
            supplier_id=payload.supplier_id,
            external_id=payload.external_id,
            mapped_by=user,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLIER_MAPPING,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supplier-mappings/bulk",
    response_model=SupplierMappingBulkCreateResponse,
    operation_id=BULK_CREATE_SUPPLIER_MAPPINGS,
)
async def create_supplier_mappings_bulk(
    payload: SupplierMappingBulkCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    return await SupplierMappingService.create_bulk_mappings(
        session=session,
        items=[i.model_dump() for i in payload.items],
        mapped_by=user,
        skip_conflicts=payload.skip_conflicts,
    )


@router.delete("/supplier-mappings/{mapping_id}", operation_id=DELETE_SUPPLIER_MAPPING)
async def delete_supplier_mapping(
    mapping_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    ok = await SupplierMappingService.delete_mapping(session, mapping_id)
    if not ok:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_SUPPLIER_MAPPING,
            error_code=BAD_REQUEST,
            message="Mapping not found",
        )
    return {"ok": True}


@router.get(
    "/products/{product_id}/supplier-offers",
    response_model=SupplierOfferListResponse,
    operation_id=GET_PRODUCT_SUPPLIER_OFFERS,
)
async def get_product_supplier_offers(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierMappingService.list_product_offers(session, product_id)


@router.put(
    "/products/{product_id}/local-stock",
    response_model=ProductLocalStockResponse,
    operation_id=UPSERT_PRODUCT_LOCAL_STOCK,
)
async def upsert_product_local_stock(
    product_id: int,
    payload: ProductLocalStockPayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    try:
        return await SupplierMappingService.upsert_vitebsk_stock(
            session=session,
            product_id=product_id,
            qty=int(payload.qty),
            updated_by=user,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=UPSERT_PRODUCT_LOCAL_STOCK,
            error_code=PRODUCT_NOT_FOUND,
            message=str(exc),
        ) from exc
