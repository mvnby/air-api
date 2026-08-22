from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, get_current_username
from routers.manager_operation_ids import (
    LIST_MANAGER_ANALYTICS_CONNECTIONS,
    UPSERT_MANAGER_YANDEX_METRIKA_CONNECTION,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_analytics import (
    AnalyticsConnectionItem,
    AnalyticsConnectionListResponse,
    YandexMetrikaConnectionUpsertPayload,
)
from services.analytics_connection_service import (
    AnalyticsConnectionError,
    AnalyticsConnectionService,
)


router = APIRouter(
    prefix="/api/manager/analytics-connections",
    tags=["manager-analytics-connections"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "",
    response_model=AnalyticsConnectionListResponse,
    operation_id=LIST_MANAGER_ANALYTICS_CONNECTIONS,
)
async def list_manager_analytics_connections(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsConnectionListResponse:
    tenant_scope = auth.tenant_scope()
    return AnalyticsConnectionListResponse(
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
        items=await AnalyticsConnectionService.list_connections(
            session,
            tenant_scope=tenant_scope,
        ),
    )


@router.put(
    "/yandex-metrika",
    response_model=AnalyticsConnectionItem,
    operation_id=UPSERT_MANAGER_YANDEX_METRIKA_CONNECTION,
)
async def upsert_manager_yandex_metrika_connection(
    payload: YandexMetrikaConnectionUpsertPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsConnectionItem:
    token = payload.oauth_token.get_secret_value() if payload.oauth_token else None
    try:
        return await AnalyticsConnectionService().upsert_yandex_metrika(
            session,
            tenant_scope=auth.tenant_scope(),
            counter_id=payload.counter_id,
            oauth_token=token,
            actor_staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
        )
    except AnalyticsConnectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error_code": exc.code, "message": str(exc)},
        ) from exc
