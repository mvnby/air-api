from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access, require_owner_access
from routers.manager_operation_ids import (
    GET_MANAGER_DOCUMENT_DRIVE_AUTHORIZATION_URL,
    GET_MANAGER_DOCUMENT_DRIVE_STATUS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_document_drive import (
    DocumentDriveAuthorizationUrlResponse,
    DocumentDriveStatusResponse,
)
from services.analytics_oauth_state import pending_actor_scope
from services.document_drive_connection_service import DocumentDriveConnectionService
from services.document_drive_contracts import DocumentDriveConnectionError
from services.document_drive_oauth_redirect import (
    resolve_document_drive_oauth_redirect_uri,
)
from services.document_drive_oauth_state import (
    DOCUMENT_DRIVE_OAUTH_SESSION_KEY,
    consume_document_drive_oauth_state,
    start_document_drive_oauth_state,
)
from services.document_drive_provider import get_document_drive_provider
from services.google_oauth_redirect import GoogleOAuthRedirectConfigurationError


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/manager/document-drive",
    tags=["manager-document-drive"],
    route_class=ManagerPermissionRoute,
)


def _callback_uri(request: Request) -> str:
    return resolve_document_drive_oauth_redirect_uri(
        request_callback_uri=str(request.url_for("manager_google_auth_callback")),
    )


def _oauth_html(*, success: bool, message: str, status_code: int) -> HTMLResponse:
    event = "connected" if success else "failed"
    title = "Google Диск подключён" if success else "Не удалось подключить Google Диск"
    return HTMLResponse(
        content=f"""
        <!doctype html><html lang="ru"><body>
          <h1>{title}</h1><p>{message}</p>
          <p><a href="/manager/settings/documents">Вернуться к настройкам документов</a></p>
          <script>
            if (window.opener) {{
              window.opener.postMessage({{"type":"mvn-document-drive","status":"{event}"}}, window.location.origin);
            }}
            window.close();
          </script>
        </body></html>
        """,
        status_code=status_code,
    )


@router.get(
    "/status",
    response_model=DocumentDriveStatusResponse,
    operation_id=GET_MANAGER_DOCUMENT_DRIVE_STATUS,
)
async def get_manager_document_drive_status(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentDriveStatusResponse:
    return await DocumentDriveConnectionService.status(
        session,
        tenant_scope=auth.tenant_scope(),
    )


@router.get(
    "/authorization-url",
    response_model=DocumentDriveAuthorizationUrlResponse,
    operation_id=GET_MANAGER_DOCUMENT_DRIVE_AUTHORIZATION_URL,
)
async def get_manager_document_drive_authorization_url(
    request: Request,
    auth: AuthenticatedUser = Depends(require_owner_access),
) -> DocumentDriveAuthorizationUrlResponse:
    try:
        redirect_uri = _callback_uri(request)
        state = start_document_drive_oauth_state(
            request,
            auth=auth,
            redirect_uri=redirect_uri,
        )
        provider = get_document_drive_provider()
        url = await run_in_threadpool(
            lambda: provider.authorization_url(
                redirect_uri=redirect_uri,
                state=state,
            )
        )
        return DocumentDriveAuthorizationUrlResponse(url=url)
    except GoogleOAuthRedirectConfigurationError as exc:
        request.session.pop(DOCUMENT_DRIVE_OAUTH_SESSION_KEY, None)
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "google_oauth_not_configured",
                "message": "Подключение Google Диска не настроено на сервере",
            },
        ) from exc
    except DocumentDriveConnectionError as exc:
        request.session.pop(DOCUMENT_DRIVE_OAUTH_SESSION_KEY, None)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error_code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/callback", include_in_schema=False, name="manager_document_drive_callback")
async def manager_document_drive_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
    code: str = "",
    state: str = "",
    error: str = "",
) -> HTMLResponse:
    pending = consume_document_drive_oauth_state(request, state)
    if pending is None:
        return _oauth_html(
            success=False,
            message="Сеанс авторизации отсутствует, истёк или уже использован.",
            status_code=400,
        )
    return await complete_manager_document_drive_oauth(
        request=request,
        session=session,
        pending=pending,
        code=code,
        error=error,
    )


async def complete_manager_document_drive_oauth(
    *,
    request: Request,
    session: AsyncSession,
    pending: dict,
    code: str,
    error: str,
) -> HTMLResponse:
    scope = await pending_actor_scope(session, pending)
    if scope is None:
        return _oauth_html(
            success=False,
            message="У пользователя больше нет доступа к настройкам этой организации.",
            status_code=403,
        )
    if error:
        return _oauth_html(
            success=False,
            message="Доступ не был предоставлен.",
            status_code=400,
        )
    normalized_code = str(code or "").strip()
    redirect_uri = str(pending.get("redirect_uri") or "")
    try:
        current_redirect_uri = _callback_uri(request)
    except GoogleOAuthRedirectConfigurationError:
        return _oauth_html(
            success=False,
            message="Подключение Google Диска не настроено на сервере.",
            status_code=503,
        )
    if (
        not normalized_code
        or not redirect_uri
        or not secrets.compare_digest(redirect_uri, current_redirect_uri)
    ):
        return _oauth_html(
            success=False,
            message="Google вернул некорректный ответ авторизации.",
            status_code=400,
        )
    provider = get_document_drive_provider()
    try:
        credentials = await run_in_threadpool(
            lambda: provider.exchange_code(
                redirect_uri=redirect_uri,
                code=normalized_code,
            )
        )
        await DocumentDriveConnectionService.complete_authorization(
            session,
            tenant_scope=scope,
            credentials=credentials,
            actor_staff_user_id=(
                int(pending["staff_user_id"])
                if pending.get("staff_user_id") is not None
                else None
            ),
            actor_username=str(pending.get("username") or ""),
            provider=provider,
        )
    except DocumentDriveConnectionError as exc:
        logger.warning(
            "Document Drive OAuth completion failed error_code=%s",
            exc.code,
        )
        return _oauth_html(
            success=False,
            message="Google Диск не подтвердил подключение. Попробуйте ещё раз.",
            status_code=exc.status_code,
        )
    except Exception as exc:
        logger.error(
            "Document Drive OAuth completion failed error_type=%s",
            type(exc).__name__,
        )
        return _oauth_html(
            success=False,
            message="Сервис Google временно недоступен.",
            status_code=502,
        )
    return _oauth_html(
        success=True,
        message="Можно закрыть эту вкладку и продолжить работу в CRM.",
        status_code=200,
    )
