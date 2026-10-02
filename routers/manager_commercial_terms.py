"""Commercial source evidence and editable, explicitly confirmed proposals."""
from routers.manager_operation_ids import (
    GET_MANAGER_ORDER_COMMERCIAL_TERMS,
    UPDATE_MANAGER_ORDER_COMMERCIAL_TERMS,
    EXTRACT_MANAGER_ORDER_COMMERCIAL_TERMS,
    GET_MANAGER_ORDER_COMMERCIAL_DOCUMENT_DEFAULTS,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from schemas_commercial_terms import ManagerCommercialDocumentDefaults, ManagerCommercialTermsResponse, ManagerCommercialTermsUpdate, ManagerCommercialTermsExtract
from services.order_commercial_terms_service import CommercialTermsRevisionConflict, OrderCommercialTermsService

router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


def error(exc: Exception) -> HTTPException:
    code = 409 if isinstance(exc, CommercialTermsRevisionConflict) else 403 if isinstance(exc, PermissionError) else 404
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/{order_id}/commercial-terms", response_model=ManagerCommercialTermsResponse, operation_id=GET_MANAGER_ORDER_COMMERCIAL_TERMS)
async def get_terms(order_id: int, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    try:
        return await OrderCommercialTermsService.read(session, order_id=order_id, scope=scope)
    except LookupError as exc:
        raise error(exc) from exc


@router.patch("/{order_id}/commercial-terms", response_model=ManagerCommercialTermsResponse, operation_id=UPDATE_MANAGER_ORDER_COMMERCIAL_TERMS)
async def update_terms(order_id: int, payload: ManagerCommercialTermsUpdate, username: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    try:
        return await OrderCommercialTermsService.update(session, order_id=order_id, scope=scope, payload=payload, username=username)
    except (LookupError, PermissionError, CommercialTermsRevisionConflict) as exc:
        raise error(exc) from exc


@router.post("/{order_id}/commercial-terms/extract", response_model=ManagerCommercialTermsResponse, operation_id=EXTRACT_MANAGER_ORDER_COMMERCIAL_TERMS)
async def extract_terms(order_id: int, payload: ManagerCommercialTermsExtract, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    try:
        return await OrderCommercialTermsService.extract(session, order_id=order_id, scope=scope, attachment_ids=payload.attachment_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (LookupError, PermissionError) as exc:
        raise error(exc) from exc


@router.get("/{order_id}/commercial-terms/document-defaults", response_model=ManagerCommercialDocumentDefaults, operation_id=GET_MANAGER_ORDER_COMMERCIAL_DOCUMENT_DEFAULTS)
async def get_defaults(order_id: int, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    try:
        terms = await OrderCommercialTermsService.read(session, order_id=order_id, scope=scope)
        return ManagerCommercialDocumentDefaults(order_id=order_id, revision=terms.revision, business_terms=terms.proposed if terms.confirmed else None)
    except LookupError as exc:
        raise error(exc) from exc
