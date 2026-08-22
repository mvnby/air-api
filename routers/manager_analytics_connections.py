from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, get_current_username
from routers.manager_operation_ids import (
    LIST_MANAGER_ANALYTICS_CONNECTIONS,
    START_MANAGER_GOOGLE_ADS_AUTHORIZATION,
    START_MANAGER_GOOGLE_ANALYTICS_AUTHORIZATION,
    START_MANAGER_GOOGLE_SEARCH_CONSOLE_AUTHORIZATION,
    UPSERT_MANAGER_YANDEX_DIRECT_CONNECTION,
    UPSERT_MANAGER_YANDEX_METRIKA_CONNECTION,
    UPSERT_MANAGER_YANDEX_WEBMASTER_CONNECTION,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_analytics import (
    AnalyticsConnectionItem,
    AnalyticsConnectionListResponse,
    AnalyticsAuthorizationUrlResponse,
    GoogleAdsAuthorizationPayload,
    GoogleAnalyticsAuthorizationPayload,
    YandexDirectConnectionUpsertPayload,
    YandexMetrikaConnectionUpsertPayload,
    YandexWebmasterConnectionUpsertPayload,
)
from models import StorefrontDomain
from services.analytics_google_providers import build_authorization_url
from services.analytics_oauth_state import (
    ANALYTICS_GOOGLE_OAUTH_SESSION_KEY,
    start_google_oauth_state,
)
from services.google_service import get_default_oauth_redirect_uri
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


@router.put(
    "/yandex-direct",
    response_model=AnalyticsConnectionItem,
    operation_id=UPSERT_MANAGER_YANDEX_DIRECT_CONNECTION,
)
async def upsert_manager_yandex_direct_connection(
    payload: YandexDirectConnectionUpsertPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsConnectionItem:
    token = payload.oauth_token.get_secret_value() if payload.oauth_token else None
    try:
        return await AnalyticsConnectionService().upsert_yandex_direct(
            session,
            tenant_scope=auth.tenant_scope(),
            client_login=payload.client_login,
            oauth_token=token,
            actor_staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
        )
    except AnalyticsConnectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error_code": exc.code, "message": str(exc)},
        ) from exc


@router.put(
    "/yandex-webmaster",
    response_model=AnalyticsConnectionItem,
    operation_id=UPSERT_MANAGER_YANDEX_WEBMASTER_CONNECTION,
)
async def upsert_manager_yandex_webmaster_connection(
    payload: YandexWebmasterConnectionUpsertPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsConnectionItem:
    token = payload.oauth_token.get_secret_value() if payload.oauth_token else None
    try:
        return await AnalyticsConnectionService().upsert_yandex_webmaster(
            session,
            tenant_scope=auth.tenant_scope(),
            oauth_token=token,
            actor_staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
        )
    except AnalyticsConnectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error_code": exc.code, "message": str(exc)},
        ) from exc


def _start_google_authorization(
    request: Request,
    *,
    auth: AuthenticatedUser,
    provider: str,
    public_config: dict[str, str],
) -> AnalyticsAuthorizationUrlResponse:
    if provider == "google_ads" and not settings.GOOGLE_ADS_DEVELOPER_TOKEN.strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "google_ads_system_not_configured",
                "message": "Google Ads ещё не настроен на стороне CRM",
            },
        )
    redirect_uri = get_default_oauth_redirect_uri()
    state = start_google_oauth_state(
        request,
        auth=auth,
        provider=provider,
        public_config=public_config,
        redirect_uri=redirect_uri,
    )
    try:
        url = build_authorization_url(provider, redirect_uri, state)
    except Exception as exc:
        request.session.pop(ANALYTICS_GOOGLE_OAUTH_SESSION_KEY, None)
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "google_oauth_unavailable",
                "message": "Google OAuth временно недоступен",
            },
        ) from exc
    return AnalyticsAuthorizationUrlResponse(url=url)


@router.post(
    "/google-analytics/authorization-url",
    response_model=AnalyticsAuthorizationUrlResponse,
    operation_id=START_MANAGER_GOOGLE_ANALYTICS_AUTHORIZATION,
)
async def start_manager_google_analytics_authorization(
    payload: GoogleAnalyticsAuthorizationPayload,
    request: Request,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsAuthorizationUrlResponse:
    return _start_google_authorization(
        request,
        auth=auth,
        provider="google_analytics",
        public_config={"property_id": payload.property_id},
    )


@router.post(
    "/google-search-console/authorization-url",
    response_model=AnalyticsAuthorizationUrlResponse,
    operation_id=START_MANAGER_GOOGLE_SEARCH_CONSOLE_AUTHORIZATION,
)
async def start_manager_google_search_console_authorization(
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsAuthorizationUrlResponse:
    scope = auth.tenant_scope()
    domain = (
        await session.execute(
            select(StorefrontDomain).where(
                StorefrontDomain.storefront_id == scope.storefront_id,
                StorefrontDomain.is_primary.is_(True),
                StorefrontDomain.status == "active",
            )
        )
    ).scalar_one_or_none()
    if domain is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "storefront_domain_unavailable",
                "message": "У филиала не настроен активный основной домен",
            },
        )
    return _start_google_authorization(
        request,
        auth=auth,
        provider="google_search_console",
        public_config={"primary_hostname": domain.hostname},
    )


@router.post(
    "/google-ads/authorization-url",
    response_model=AnalyticsAuthorizationUrlResponse,
    operation_id=START_MANAGER_GOOGLE_ADS_AUTHORIZATION,
)
async def start_manager_google_ads_authorization(
    payload: GoogleAdsAuthorizationPayload,
    request: Request,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AnalyticsAuthorizationUrlResponse:
    return _start_google_authorization(
        request,
        auth=auth,
        provider="google_ads",
        public_config={
            "customer_id": payload.customer_id,
            "login_customer_id": payload.login_customer_id or "",
        },
    )
