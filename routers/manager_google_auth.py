import logging
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.database import get_session
from core.security import (
    OWNER_ACCESS_ROLES,
    AuthenticatedUser,
    get_current_owner_username,
    require_owner_access,
)
from models import Tenant, TenantMembership
from routers.manager_operation_ids import (
    GET_MANAGER_GOOGLE_AUTH_STATUS,
    GET_MANAGER_GOOGLE_AUTH_URL,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import ManagerGoogleAuthStatusResponse, ManagerGoogleAuthUrlResponse
from services.google_service import get_google_service
from services.staff_user_service import StaffUserService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard


logger = logging.getLogger(__name__)

GOOGLE_OAUTH_SESSION_KEY = "manager_google_oauth_pending"
GOOGLE_OAUTH_STATE_TTL_SECONDS = 10 * 60
GOOGLE_OAUTH_UNAVAILABLE_MESSAGE = "Google authentication service is unavailable"
GOOGLE_OAUTH_CONFIGURATION_MESSAGE = "Google OAuth redirect URI is not configured"


class GoogleOAuthConfigurationError(RuntimeError):
    pass


router = APIRouter(
    prefix="/api/manager/google-auth",
    tags=["manager/google-auth"],
    route_class=ManagerPermissionRoute,
)


def _google_oauth_redirect_uri(request: Request) -> str:
    configured = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    if settings.is_production:
        raise GoogleOAuthConfigurationError(GOOGLE_OAUTH_CONFIGURATION_MESSAGE)
    return str(request.url_for("manager_google_auth_callback"))


def _oauth_now() -> float:
    return time.time()


def _constant_time_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _oauth_html_response(*, title: str, message: str, status_code: int) -> HTMLResponse:
    return HTMLResponse(
        content=f"""
        <html><body>
            <h1>{title}</h1>
            <p>{message}</p>
            <p><a href="/manager/settings">Back to manager settings</a></p>
        </body></html>
        """,
        status_code=status_code,
    )


def _consume_google_oauth_state(request: Request, received_state: str) -> dict[str, object] | None:
    pending = request.session.get(GOOGLE_OAUTH_SESSION_KEY)
    if not isinstance(pending, dict):
        return None

    expected_state = str(pending.get("state") or "")
    redirect_uri = str(pending.get("redirect_uri") or "")
    try:
        issued_at = float(pending.get("issued_at"))
    except (TypeError, ValueError):
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        return None

    age_seconds = _oauth_now() - issued_at
    if (
        not expected_state
        or not redirect_uri
        or age_seconds < 0
        or age_seconds > GOOGLE_OAUTH_STATE_TTL_SECONDS
    ):
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        return None

    state = str(received_state or "")
    if not state or not _constant_time_equal(expected_state, state):
        return None

    current_redirect_uri = _google_oauth_redirect_uri(request)
    if not _constant_time_equal(redirect_uri, current_redirect_uri):
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        return None

    # Consume before the provider exchange so the callback is single-use even
    # when the provider request fails.
    request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
    return {
        "redirect_uri": redirect_uri,
        "auth_source": str(pending.get("auth_source") or ""),
        "auth_version": pending.get("auth_version"),
        "staff_user_id": pending.get("staff_user_id"),
        "username": str(pending.get("username") or ""),
    }


async def _oauth_owner_binding_is_active(
    session: AsyncSession,
    pending: dict[str, object],
) -> bool:
    auth_source = str(pending.get("auth_source") or "")
    username = str(pending.get("username") or "")
    staff_user_id = pending.get("staff_user_id")

    if auth_source == "legacy":
        if not LegacyOwnerAuthGuard.configured_username_matches(username):
            return False
        state = await LegacyOwnerAuthGuard.state(session)
        return LegacyOwnerAuthGuard.allows_legacy_token(
            state,
            token_version=pending.get("auth_version"),
        )
    if staff_user_id is None:
        return False
    try:
        staff_user = await StaffUserService.get_by_id(session, int(staff_user_id))
    except (TypeError, ValueError):
        return False
    if staff_user is None or not StaffUserService.is_active(staff_user):
        return False
    try:
        pending_auth_version = int(pending.get("auth_version"))
    except (TypeError, ValueError):
        return False
    if pending_auth_version != int(staff_user.auth_version):
        return False
    if LegacyOwnerAuthGuard.configured_username_matches(username):
        state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_bound_staff(
            state,
            staff_user_id=int(staff_user.id or 0),
        ):
            return False
    if StaffUserService.primary_role(staff_user).strip().lower() not in OWNER_ACCESS_ROLES:
        return False

    try:
        membership_id = int(pending.get("tenant_membership_id"))
        tenant_id = int(pending.get("tenant_id"))
    except (TypeError, ValueError):
        return False
    if membership_id <= 0 or tenant_id <= 0:
        return False

    statement = (
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.id == membership_id,
            TenantMembership.staff_user_id == int(staff_user_id),
            TenantMembership.tenant_id == tenant_id,
        )
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return False
    membership, tenant = row
    return (
        str(membership.status or "").strip().lower() == "active"
        and str(membership.role or "").strip().lower() in OWNER_ACCESS_ROLES
        and str(tenant.status or "").strip().lower() == "active"
        and bool(tenant.is_system)
    )


@router.get("/status", response_model=ManagerGoogleAuthStatusResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_STATUS)
async def get_manager_google_auth_status(_: str = Depends(get_current_owner_username)):
    try:
        status_payload = await run_in_threadpool(lambda: get_google_service().get_token_status())
    except Exception as exc:
        logger.error(
            "Failed to read Google authentication status error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail=GOOGLE_OAUTH_UNAVAILABLE_MESSAGE) from exc
    return ManagerGoogleAuthStatusResponse(**status_payload)


@router.get("/url", response_model=ManagerGoogleAuthUrlResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_URL)
async def get_manager_google_auth_url(
    request: Request,
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    state = secrets.token_urlsafe(32)
    try:
        redirect_uri = _google_oauth_redirect_uri(request)
        request.session[GOOGLE_OAUTH_SESSION_KEY] = {
            "state": state,
            "issued_at": _oauth_now(),
            "redirect_uri": redirect_uri,
            "auth_source": auth.auth_source,
            "auth_version": auth.auth_version,
            "staff_user_id": auth.staff_user_id,
            "username": auth.username,
            "tenant_membership_id": auth.tenant_membership_id,
            "tenant_id": auth.tenant_id,
        }
        url = await run_in_threadpool(
            lambda: get_google_service().get_auth_url(redirect_uri, state=state)
        )
        return ManagerGoogleAuthUrlResponse(url=url)
    except GoogleOAuthConfigurationError as exc:
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        raise HTTPException(status_code=503, detail=GOOGLE_OAUTH_CONFIGURATION_MESSAGE) from exc
    except Exception as exc:
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        logger.error(
            "Failed to start Google authentication error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail=GOOGLE_OAUTH_UNAVAILABLE_MESSAGE) from exc


@router.get("/callback", include_in_schema=False)
async def manager_google_auth_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
    code: str = "",
    state: str = "",
    error: str = "",
):
    try:
        pending = _consume_google_oauth_state(request, state)
    except GoogleOAuthConfigurationError:
        request.session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
        return _oauth_html_response(
            title="Google authentication is not configured",
            message=GOOGLE_OAUTH_CONFIGURATION_MESSAGE,
            status_code=503,
        )

    if pending is None:
        return _oauth_html_response(
            title="Google authentication failed",
            message="Authorization session is missing, invalid, expired, or already used.",
            status_code=400,
        )

    if not await _oauth_owner_binding_is_active(session, pending):
        return _oauth_html_response(
            title="Google authentication failed",
            message="The owner account that started authorization is no longer active.",
            status_code=403,
        )
    redirect_uri = str(pending["redirect_uri"])

    if error:
        return _oauth_html_response(
            title="Google authentication failed",
            message="Authorization was denied or could not be completed.",
            status_code=400,
        )

    code = (code or "").strip()
    if not code:
        return _oauth_html_response(
            title="Google authentication failed",
            message="Authorization code is missing.",
            status_code=400,
        )

    try:
        await run_in_threadpool(lambda: get_google_service().finish_auth(code, redirect_uri))
    except Exception as exc:
        logger.error(
            "Failed to finish Google authentication error_type=%s",
            type(exc).__name__,
        )
        return _oauth_html_response(
            title="Google authentication failed",
            message=GOOGLE_OAUTH_UNAVAILABLE_MESSAGE,
            status_code=502,
        )

    return _oauth_html_response(
        title="Google authentication updated",
        message="You can close this tab and return to manager settings.",
        status_code=200,
    )
