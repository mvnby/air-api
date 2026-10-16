"""Company staff candidates and audited optimistic order reassignment."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.order_responsibility import ManagerOrderResponsiblesResponse, ManagerOrderResponsibleUpdate
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import LIST_MANAGER_ORDER_RESPONSIBLES, PATCH_MANAGER_ORDER_RESPONSIBLE
from routers.manager_staff_invitations import require_team_origin
from schemas_manager_orders import ManagerOrderDetailResponse
from services.order_responsibility_service import OrderResponsibilityError, OrderResponsibilityService

router = APIRouter(prefix="/api/manager", tags=["manager-orders"])


@router.get("/order-responsibles", response_model=ManagerOrderResponsiblesResponse, operation_id=LIST_MANAGER_ORDER_RESPONSIBLES)
async def list_order_responsibles(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access),
):
    """List active actual owner/admin/manager members of the selected company.

    Requires a live Manager staff identity, including verified platform support.
    Does not include installers, catalog editors, virtual memberships or credentials.
    """
    try:
        return await OrderResponsibilityService.list_candidates(session, auth=auth, page=page, limit=limit)
    except OrderResponsibilityError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None


@router.patch("/orders/{order_id}/responsible", response_model=ManagerOrderDetailResponse,
              operation_id=PATCH_MANAGER_ORDER_RESPONSIBLE, dependencies=[Depends(require_team_origin)])
async def patch_order_responsible(
    payload: ManagerOrderResponsibleUpdate, order_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Assign/clear the responsible staff member within the selected company/site.

    Requires X-Kitlane-Team:1, approved Origin and live owner/admin/manager membership
    or verified platform support. Legacy emergency identities without staff return403.
    Actual active company membership is always required for a new assignee. A stale
    expected_version returns409. Real changes increment the dedicated counter and
    atomically record old/new responsibility; a no-op neither increments nor audits.
    """
    try:
        return await OrderResponsibilityService.assign(session, order_id=order_id, payload=payload, auth=auth)
    except OrderResponsibilityError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None
