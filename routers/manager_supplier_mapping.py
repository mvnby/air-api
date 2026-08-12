from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, PRODUCT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    LIST_PRODUCT_SUPPLIER_OFFER_CANDIDATES,
    PUT_SUPPLIER_OFFER_MAPPING,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_supplier_mapping import (
    SupplierOfferCandidateListResponse,
    SupplierOfferMappingPutPayload,
    SupplierOfferMappingResponse,
)
from services.supplier_offer_mapping_service import (
    SupplierOfferMappingConflictError,
    SupplierOfferMappingService,
)


POSTGRESQL_INTEGER_MAX = 2_147_483_647

router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/products/{product_id}/supplier-offer-candidates",
    response_model=SupplierOfferCandidateListResponse,
    operation_id=LIST_PRODUCT_SUPPLIER_OFFER_CANDIDATES,
)
async def list_product_supplier_offer_candidates(
    product_id: Annotated[int, Path(ge=1, le=POSTGRESQL_INTEGER_MAX)],
    supplier_id: int = Query(ge=1, le=POSTGRESQL_INTEGER_MAX),
    source_id: int | None = Query(default=None, ge=1, le=POSTGRESQL_INTEGER_MAX),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    try:
        return await SupplierOfferMappingService.list_candidates(
            session,
            product_id=product_id,
            supplier_id=supplier_id,
            source_id=source_id,
            query=q,
            page=page,
            limit=limit,
            include_inactive=include_inactive,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_PRODUCT_SUPPLIER_OFFER_CANDIDATES,
            error_code=PRODUCT_NOT_FOUND,
            message=str(exc),
        ) from exc


@router.put(
    "/supplier-offers/{offer_id}/mapping",
    response_model=SupplierOfferMappingResponse,
    operation_id=PUT_SUPPLIER_OFFER_MAPPING,
)
async def put_supplier_offer_mapping(
    offer_id: Annotated[int, Path(ge=1, le=POSTGRESQL_INTEGER_MAX)],
    payload: SupplierOfferMappingPutPayload,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_username),
):
    try:
        return await SupplierOfferMappingService.put_mapping(
            session,
            offer_id=offer_id,
            product_id=payload.product_id,
            replace_existing=payload.replace_existing,
            expected_mapping_id=payload.expected_mapping_id,
            expected_product_id=payload.expected_product_id,
            mapped_by=user,
        )
    except SupplierOfferMappingConflictError as exc:
        await session.rollback()
        raise manager_http_error(
            status_code=409,
            endpoint=PUT_SUPPLIER_OFFER_MAPPING,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        await session.rollback()
        message = str(exc)
        status_code = 404 if message.endswith("not found") else 400
        error_code = PRODUCT_NOT_FOUND if message == "Product not found" else BAD_REQUEST
        raise manager_http_error(
            status_code=status_code,
            endpoint=PUT_SUPPLIER_OFFER_MAPPING,
            error_code=error_code,
            message=message,
        ) from exc
