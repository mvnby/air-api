"""Read the print composition of one proposal without changing its products."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.context_builder import (
    DocumentContextBuilder,
    DocumentContextError,
)
from modules.documents.application.errors import ManagedDocumentNotFoundError
from modules.documents.domain.waybill_composition import WaybillCompositionSource
from routers.manager_operation_ids import GET_MANAGER_WAYBILL_COMPOSITION
from routers.manager_permission_policy import ManagerPermissionRoute

router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/orders/{order_id}/waybill-composition",
    response_model=WaybillCompositionSource,
    operation_id=GET_MANAGER_WAYBILL_COMPOSITION,
)
async def get_manager_waybill_composition(
    order_id: int,
    proposal_id: int | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Read the current tenant/storefront order's TN-2 or TTN-1 source lines, quantities and saved
    or catalog component prices. Pass the source revision with line choices on draft creation.
    No order, document or number is created. Manager access is required. A missing or out-of-scope
    order returns 404, an unavailable proposal returns 400.
    """
    try:
        return await DocumentContextBuilder.waybill_source(
            session,
            order_id=order_id,
            tenant_scope=auth.tenant_scope(),
            proposal_id=proposal_id,
        )
    except (DocumentContextError, ManagedDocumentNotFoundError) as exc:
        raise manager_http_error(
            status_code=404 if isinstance(exc, ManagedDocumentNotFoundError) else 400,
            endpoint=GET_MANAGER_WAYBILL_COMPOSITION,
            error_code="waybill_composition_unavailable",
            message=str(exc),
        ) from exc
