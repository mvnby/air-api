"""Explicit frozen-contract choices; draft creation uses the shared lifecycle API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from core.manager_api_errors import manager_http_error
from routers.manager_permission_policy import ManagerPermissionRoute
from .amendment_schemas import AmendmentBasisList
from modules.documents.application.contract_amendments import list_bases
from modules.documents.application.errors import ManagedDocumentNotFoundError


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/orders/{order_id}/contract-amendments/bases",
    response_model=AmendmentBasisList,
    operation_id="list_manager_contract_amendment_bases",
)
async def list_contract_amendment_bases(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    limit: int = Query(default=100, ge=1, le=100),
):
    """List explicit native contract choices with frozen original amounts and current
    effective amendments for a tenant/storefront order. Requires Manager membership.
    Read-only; never chooses a basis automatically. Returns 404 for an inaccessible
    order. Legacy documents without a frozen BYN amount are excluded. Pass the
    returned revision on draft creation; changes to effective agreements return 409.
    """
    try:
        return {
            "order_id": order_id,
            "items": await list_bases(
                session, scope=auth.tenant_scope(), order_id=order_id, limit=limit
            ),
        }
    except ManagedDocumentNotFoundError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint="list_manager_contract_amendment_bases",
            error_code="managed_document_order_not_found",
            message=str(exc),
        )
