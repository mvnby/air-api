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
    """
    Read customer-requested source evidence separately from proposed business terms, review
    confirmation and current revision. Missing or inaccessible order returns 404. Reading
    fallback evidence does not save or confirm it.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderCommercialTermsService.read(session, order_id=order_id, scope=scope)
    except LookupError as exc:
        raise error(exc) from exc


@router.patch("/{order_id}/commercial-terms", response_model=ManagerCommercialTermsResponse, operation_id=UPDATE_MANAGER_ORDER_COMMERCIAL_TERMS)
async def update_terms(order_id: int, payload: ManagerCommercialTermsUpdate, username: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """
    Save proposed business terms and their confirmation under an order lock.
    expected_revision must match or the command returns 409; each successful edit increments
    the revision, so replaying an old revision conflicts. Missing order returns 404 and demo
    mutations return 403. Source evidence is preserved independently of the negotiated
    terms.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderCommercialTermsService.update(session, order_id=order_id, scope=scope, payload=payload, username=username)
    except (LookupError, PermissionError, CommercialTermsRevisionConflict) as exc:
        raise error(exc) from exc


@router.post("/{order_id}/commercial-terms/extract", response_model=ManagerCommercialTermsResponse, operation_id=EXTRACT_MANAGER_ORDER_COMMERCIAL_TERMS)
async def extract_terms(order_id: int, payload: ManagerCommercialTermsExtract, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """
    Extract customer-requested commercial conditions from saved order source context and up
    to eight selected scoped order attachments, then merge source evidence with duplicate
    evidence suppressed. Proposed business terms, review confirmation and revision are
    preserved. Missing order/attachment returns 404, invalid extraction input 400 and demo
    mutation 403. This saves extracted evidence; it does not accept those conditions or
    change document defaults.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderCommercialTermsService.extract(session, order_id=order_id, scope=scope, attachment_ids=payload.attachment_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (LookupError, PermissionError) as exc:
        raise error(exc) from exc


@router.get("/{order_id}/commercial-terms/document-defaults", response_model=ManagerCommercialDocumentDefaults, operation_id=GET_MANAGER_ORDER_COMMERCIAL_DOCUMENT_DEFAULTS)
async def get_defaults(order_id: int, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """
    Read document defaults derived from the order’s reviewed commercial terms. Business
    terms are returned only when the proposed terms are valid and confirmed; otherwise they
    are absent. Missing or inaccessible order returns 404; this does not create a document
    or confirm terms.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        terms = await OrderCommercialTermsService.read(session, order_id=order_id, scope=scope)
        return ManagerCommercialDocumentDefaults(order_id=order_id, revision=terms.revision, business_terms=terms.proposed if terms.confirmed else None)
    except LookupError as exc:
        raise error(exc) from exc
