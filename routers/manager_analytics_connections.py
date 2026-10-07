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
from services.google_oauth_redirect import (
    GoogleOAuthRedirectConfigurationError,
    resolve_google_oauth_redirect_uri,
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
    """
    Read analytics-provider connection states and public configuration for the current
    tenant/storefront; requires a current-tenant owner/admin. Includes available/unconfigured
    providers and stored verification/error state, without tokens. Reads may detect unreadable
    stored credentials; connected status does not constitute a new live provider verification.
    This does not use the platform Google Drive credentials.
    """
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
    """
    Verify the supplied Yandex Metrika counter/token with the provider, then save encrypted
    credentials and public counter metadata for the current storefront with an audit event.
    Requires a current-tenant owner/admin. A blank or omitted token reuses stored credentials;
    first connection requires a token. Validation/provider failures use
    detail.error_code/message and do not confirm a connection. Repeats re-verify and save; no
    command replay receipt is provided.
    """
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
    """
    Verify Yandex Direct access for the optional client_login, then save encrypted
    credentials/public configuration for the current tenant/storefront and audit the change.
    Requires a current-tenant owner/admin. A blank/omitted token reuses this storefront's stored
    token; otherwise a token is required. Invalid/provider-denied configuration returns 422;
    retryable or unexpected provider failure returns 502 with detail.error_code/message.
    Repeating PUT repeats provider verification rather than replaying a receipt.
    """
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
    """
    Verify Yandex Webmaster access to the current storefront's active primary hostname, then
    store encrypted credentials/public configuration and audit the change. Requires a
    current-tenant owner/admin; the caller cannot supply another storefront's hostname.
    Blank/omitted token reuses stored credentials. Missing primary domain or denied/unverified
    access returns 422; retryable provider failure returns 502 with detail.error_code/message.
    Repeats re-verify the connection; no command replay receipt exists.
    """
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
    try:
        redirect_uri = resolve_google_oauth_redirect_uri(
            request_callback_uri=str(request.url_for("manager_google_auth_callback")),
            runtime_settings=settings,
        )
    except GoogleOAuthRedirectConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "google_oauth_redirect_not_configured",
                "message": "Google OAuth не настроен для рабочего адреса CRM",
            },
        ) from exc
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
    """
    Begin Google Analytics authorization for property_id in the current tenant/storefront;
    requires a current-tenant owner/admin. Returns a consent URL and replaces pending analytics
    OAuth state in the browser session, bound to actor/scope and provider configuration.
    Complete the callback in that cookie session to save credentials; this request does not
    connect the provider yet. Configuration/unavailable OAuth returns 503 with
    detail.error_code/message. Starting another analytics flow supersedes the pending one.
    """
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
    """
    Begin Google Search Console authorization for the current storefront's active primary
    hostname; requires a current-tenant owner/admin. Missing primary domain returns 422 with
    storefront_domain_unavailable. Returns a consent URL and replaces browser-session analytics
    state; credentials are saved only after the callback and provider verification in that
    session. OAuth configuration/unavailability returns 503. The hostname is server-resolved,
    and a later analytics authorization replaces this pending flow.
    """
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
    """
    Begin Google Ads authorization for customer_id and optional login_customer_id in the current
    storefront; requires a current-tenant owner/admin. A configured platform developer token is
    required or returns 503 with google_ads_system_not_configured. Returns a consent URL and
    replaces actor/scope-bound analytics state in the browser session. Complete the callback in
    that cookie session to verify and save the connection; this request alone does not save
    credentials. Other OAuth configuration/unavailability failures also return 503.
    """
    return _start_google_authorization(
        request,
        auth=auth,
        provider="google_ads",
        public_config={
            "customer_id": payload.customer_id,
            "login_customer_id": payload.login_customer_id or "",
        },
    )
