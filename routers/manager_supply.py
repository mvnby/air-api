from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, PRODUCT_NOT_FOUND
from core.security import AuthenticatedUser, get_current_username, require_manager_access
from routers.manager_operation_ids import (
    ANALYZE_SUPPLIER_SOURCE,
    BULK_CREATE_SUPPLIER_MAPPINGS,
    CREATE_STOCK_SUPPLY_REQUEST,
    CREATE_SUPPLIER,
    CREATE_SUPPLIER_CONTACT,
    CREATE_SUPPLIER_MAPPING,
    CREATE_SUPPLIER_SOURCE,
    CREATE_SUPPLIER_WAREHOUSE,
    CREATE_SUPPLY_REQUEST,
    CREATE_SUPPLY_REQUEST_FROM_ORDER_LINES,
    DELETE_SUPPLIER,
    DELETE_SUPPLIER_CONTACT,
    DELETE_SUPPLIER_SOURCE,
    DELETE_SUPPLIER_MAPPING,
    DELETE_SUPPLIER_WAREHOUSE,
    GENERATE_SUPPLY_LOGISTICS_MESSAGE,
    GENERATE_SUPPLY_REQUEST_SUPPLIER_MESSAGE,
    GET_PRODUCT_SUPPLIER_OFFERS,
    LIST_SUPPLIER_SOURCE_URL_IMPORT_CANDIDATES,
    LIST_SUPPLIER_CONTACTS,
    LIST_SUPPLIER_SHEETS,
    LIST_SUPPLIERS,
    LIST_SUPPLIER_SOURCES,
    LIST_SUPPLIER_WAREHOUSES,
    LIST_SUPPLY_REQUESTS,
    START_SUPPLIER_SOURCE_URL_IMPORT,
    SUGGEST_SUPPLIER_OFFERS,
    SYNC_ALL_SUPPLIER_SOURCES,
    LIST_UNMAPPED_SUPPLIER_OFFERS,
    PATCH_SUPPLIER,
    PATCH_SUPPLIER_CONTACT,
    PATCH_SUPPLIER_SOURCE,
    PATCH_SUPPLIER_WAREHOUSE,
    PATCH_SUPPLY_REQUEST,
    PATCH_SUPPLY_REQUEST_LINE,
    SYNC_SUPPLIER_SOURCE,
    UPSERT_PRODUCT_LOCAL_STOCK,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    CatalogImportJobStartResponse,
    ProductLocalStockPayload,
    ProductLocalStockResponse,
    SupplierContactCreatePayload,
    SupplierContactListResponse,
    SupplierContactResponse,
    SupplierContactUpdatePayload,
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
    SupplierWarehouseCreatePayload,
    SupplierWarehouseListResponse,
    SupplierWarehouseResponse,
    SupplierWarehouseUpdatePayload,
    SupplyLogisticsMessagePayload,
    SupplyMessageResponse,
    SupplyRequestCreatePayload,
    SupplyRequestCreateResponse,
    SupplyRequestFromOrderLinesPayload,
    SupplyRequestLineUpdatePayload,
    SupplyRequestListResponse,
    SupplyRequestMessagePayload,
    SupplyRequestResponse,
    SupplyRequestStockCreatePayload,
    SupplyRequestUpdatePayload,
)
from services.catalog_import_runtime_service import catalog_import_runtime_service
from services.supplier_mapping_service import SupplierCatalogService, SupplierMappingService
from services.supplier_sync_service import SupplierSyncService
from services.supply_request_service import SupplierProfileService, SupplyRequestService


router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


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


@router.get(
    "/suppliers/{supplier_id}/contacts",
    response_model=SupplierContactListResponse,
    operation_id=LIST_SUPPLIER_CONTACTS,
)
async def list_supplier_contacts(
    supplier_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierProfileService.list_contacts(session, supplier_id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_SUPPLIER_CONTACTS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/suppliers/{supplier_id}/contacts",
    response_model=SupplierContactResponse,
    operation_id=CREATE_SUPPLIER_CONTACT,
)
async def create_supplier_contact(
    supplier_id: int,
    payload: SupplierContactCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierProfileService.create_contact(session, supplier_id, payload.model_dump())
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLIER_CONTACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/suppliers/{supplier_id}/contacts/{contact_id}",
    response_model=SupplierContactResponse,
    operation_id=PATCH_SUPPLIER_CONTACT,
)
async def patch_supplier_contact(
    supplier_id: int,
    contact_id: int,
    payload: SupplierContactUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        result = await SupplierProfileService.update_contact(
            session,
            supplier_id,
            contact_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLIER_CONTACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_SUPPLIER_CONTACT,
            error_code=BAD_REQUEST,
            message="Supplier contact not found",
        )
    return result


@router.delete(
    "/suppliers/{supplier_id}/contacts/{contact_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_SUPPLIER_CONTACT,
)
async def delete_supplier_contact(
    supplier_id: int,
    contact_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    ok = await SupplierProfileService.delete_contact(session, supplier_id, contact_id)
    if not ok:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_SUPPLIER_CONTACT,
            error_code=BAD_REQUEST,
            message="Supplier contact not found",
        )
    return {"message": "Контакт удалён"}


@router.get(
    "/suppliers/{supplier_id}/warehouses",
    response_model=SupplierWarehouseListResponse,
    operation_id=LIST_SUPPLIER_WAREHOUSES,
)
async def list_supplier_warehouses(
    supplier_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierProfileService.list_warehouses(session, supplier_id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_SUPPLIER_WAREHOUSES,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/suppliers/{supplier_id}/warehouses",
    response_model=SupplierWarehouseResponse,
    operation_id=CREATE_SUPPLIER_WAREHOUSE,
)
async def create_supplier_warehouse(
    supplier_id: int,
    payload: SupplierWarehouseCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierProfileService.create_warehouse(session, supplier_id, payload.model_dump())
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLIER_WAREHOUSE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/suppliers/{supplier_id}/warehouses/{warehouse_id}",
    response_model=SupplierWarehouseResponse,
    operation_id=PATCH_SUPPLIER_WAREHOUSE,
)
async def patch_supplier_warehouse(
    supplier_id: int,
    warehouse_id: int,
    payload: SupplierWarehouseUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        result = await SupplierProfileService.update_warehouse(
            session,
            supplier_id,
            warehouse_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLIER_WAREHOUSE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_SUPPLIER_WAREHOUSE,
            error_code=BAD_REQUEST,
            message="Supplier warehouse not found",
        )
    return result


@router.delete(
    "/suppliers/{supplier_id}/warehouses/{warehouse_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_SUPPLIER_WAREHOUSE,
)
async def delete_supplier_warehouse(
    supplier_id: int,
    warehouse_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    ok = await SupplierProfileService.delete_warehouse(session, supplier_id, warehouse_id)
    if not ok:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_SUPPLIER_WAREHOUSE,
            error_code=BAD_REQUEST,
            message="Supplier warehouse not found",
        )
    return {"message": "Склад удалён"}


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
    q: Optional[str] = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await SupplierMappingService.list_unmapped(
        session=session,
        supplier_id=supplier_id,
        source_id=source_id,
        query=q,
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


@router.get(
    "/supply-requests",
    response_model=SupplyRequestListResponse,
    operation_id=LIST_SUPPLY_REQUESTS,
)
async def list_supply_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    supplier_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    order_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.list_requests(
            session,
            page=page,
            limit=limit,
            status=status,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            source_type=source_type,
            order_id=order_id,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_SUPPLY_REQUESTS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supply-requests",
    response_model=SupplyRequestCreateResponse,
    operation_id=CREATE_SUPPLY_REQUEST,
)
async def create_supply_request(
    payload: SupplyRequestCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.create_request(session, payload.model_dump(), created_by=user)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLY_REQUEST,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supply-requests/from-order-lines",
    response_model=SupplyRequestCreateResponse,
    operation_id=CREATE_SUPPLY_REQUEST_FROM_ORDER_LINES,
)
async def create_supply_request_from_order_lines(
    payload: SupplyRequestFromOrderLinesPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        return await SupplyRequestService.create_from_order_lines(
            session,
            payload.model_dump(),
            tenant_scope=auth.tenant_scope(),
            created_by=auth.username,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_SUPPLY_REQUEST_FROM_ORDER_LINES,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supply-requests/stock",
    response_model=SupplyRequestCreateResponse,
    operation_id=CREATE_STOCK_SUPPLY_REQUEST,
)
async def create_stock_supply_request(
    payload: SupplyRequestStockCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.create_stock_requests(session, payload.model_dump(), created_by=user)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_STOCK_SUPPLY_REQUEST,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/supply-requests/{request_id}",
    response_model=SupplyRequestResponse,
    operation_id=PATCH_SUPPLY_REQUEST,
)
async def patch_supply_request(
    request_id: int,
    payload: SupplyRequestUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.update_request(
            session,
            request_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLY_REQUEST,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/supply-requests/lines/{line_id}",
    response_model=SupplyRequestResponse,
    operation_id=PATCH_SUPPLY_REQUEST_LINE,
)
async def patch_supply_request_line(
    line_id: int,
    payload: SupplyRequestLineUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.update_line(
            session,
            line_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_SUPPLY_REQUEST_LINE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supply-requests/{request_id}/message/supplier",
    response_model=SupplyMessageResponse,
    operation_id=GENERATE_SUPPLY_REQUEST_SUPPLIER_MESSAGE,
)
async def generate_supply_request_supplier_message(
    request_id: int,
    payload: SupplyRequestMessagePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.generate_supplier_message(
            session,
            request_id,
            mark_sent=payload.mark_sent,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GENERATE_SUPPLY_REQUEST_SUPPLIER_MESSAGE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/supply-requests/message/logistics",
    response_model=SupplyMessageResponse,
    operation_id=GENERATE_SUPPLY_LOGISTICS_MESSAGE,
)
async def generate_supply_logistics_message(
    payload: SupplyLogisticsMessagePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplyRequestService.generate_logistics_message(
            session,
            payload.request_ids,
            mark_sent=payload.mark_sent,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GENERATE_SUPPLY_LOGISTICS_MESSAGE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
