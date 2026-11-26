from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.order_travel_route import (
    ManagerOrderTravelRouteRequest,
    ManagerOrderTravelRouteResponse,
)
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import CALCULATE_MANAGER_ORDER_TRAVEL_ROUTE
from services.manager_content_ai_limiter import ManagerContentAILimiter, ManagerContentAIRateLimitError
from services.order_travel_route_service import OrderTravelRouteError, OrderTravelRouteService
from services.tenant_entity_access_service import TenantEntityAccessService


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])
_limiter = ManagerContentAILimiter(max_requests=10, max_concurrent=4)


@router.post(
    "/{order_id}/travel-route",
    response_model=ManagerOrderTravelRouteResponse,
    operation_id=CALCULATE_MANAGER_ORDER_TRAVEL_ROUTE,
)
async def calculate_manager_order_travel_route(
    order_id: int,
    payload: ManagerOrderTravelRouteRequest,
    response: Response,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
) -> ManagerOrderTravelRouteResponse:
    """
    Estimate the driving distance and time from Vitebsk to an order's draft
    object address and back. A Manager in the system company with access to the
    order can preview a typed or selected address. The estimate does not persist
    changes or create worker payments. The provider receives the address and route points.
    """
    scope = auth.tenant_scope()
    if not scope.is_system:
        raise HTTPException(403, detail="System company access required")
    if await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope) is None:
        raise HTTPException(404, detail="Order not found")

    # The scope check is read-only. Release its database connection before the provider call.
    await session.rollback()
    try:
        async with _limiter.limit(f"{scope.tenant_id}:{auth.staff_user_id or auth.username}"):
            result = await OrderTravelRouteService.calculate(payload.address)
    except ManagerContentAIRateLimitError as exc:
        raise HTTPException(
            429,
            detail={"code": "order_route_rate_limit"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except OrderTravelRouteError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from None
    response.headers["Cache-Control"] = "private, no-store"
    return result
