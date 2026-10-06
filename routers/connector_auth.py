"""OAuth HTTP adapter and an explicit Manager-authenticated consent screen."""

import html
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.connector_security import connector_resource_metadata
from core.security import (
    AuthenticatedUser,
    get_current_auth_context,
    require_manager_access,
)
from routers import manager_operation_ids as operation_ids
from schemas_connector_auth import ConnectorGrantListResponse, ConnectorTokenResponse
from services.connector_auth_policy import (
    SCOPES,
    ConnectorAuthError,
    csrf_token,
    issuer,
    validate_csrf,
)
from services.connector_auth_service import ConnectorAuthService

router = APIRouter(tags=["connector-auth"])
CONSENT_COOKIE = "kitlane_connector_consent"
NO_CACHE = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}
HTML_HEADERS = {
    **NO_CACHE,
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
}


def _credential(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    return authorization or request.cookies.get("access_token", "")


def _error(exc: ConnectorAuthError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.error, "error_description": str(exc)},
        status_code=exc.status_code,
        headers=NO_CACHE,
    )


async def _form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";")[0]
    if content_type != "application/x-www-form-urlencoded":
        raise ConnectorAuthError("invalid_request", "Form-encoded body required")
    if len(await request.body()) > 8192:
        raise ConnectorAuthError("invalid_request", "Request body too large")
    form = await request.form()
    if any(len(form.getlist(key)) != 1 for key in form):
        raise ConnectorAuthError("invalid_request", "Duplicate form parameters")
    return {key: str(value) for key, value in form.items()}


@router.get(
    "/.well-known/oauth-authorization-server", operation_id="connector_oauth_metadata"
)
async def authorization_metadata():
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": base + "/api/connector/oauth/authorize",
        "token_endpoint": base + "/api/connector/oauth/token",
        "revocation_endpoint": base + "/api/connector/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": False,
        "authorization_response_iss_parameter_supported": True,
        "scopes_supported": sorted(SCOPES),
    }


@router.get(
    "/.well-known/oauth-protected-resource",
    operation_id="connector_oauth_resource_metadata",
)
@router.get(
    "/.well-known/oauth-protected-resource/api/connector/mcp",
    operation_id="connector_oauth_resource_path_metadata",
)
async def protected_resource_metadata():
    return connector_resource_metadata()


@router.get(
    "/api/connector/oauth/authorize",
    operation_id="connector_oauth_authorize",
    response_class=HTMLResponse,
)
async def authorize(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        # Reject parameter pollution before any state or consent is created.
        params = request.query_params
        if any(len(params.getlist(key)) != 1 for key in params):
            raise ConnectorAuthError(
                "invalid_request", "Duplicate authorization parameters"
            )
        auth = await get_current_auth_context(request, token=None, session=session)
        auth = await require_manager_access(auth)
        pending, nonce = await ConnectorAuthService.start_consent(
            session,
            auth,
            _credential(request),
            client_id=params.get("client_id", ""),
            redirect_uri=params.get("redirect_uri", ""),
            requested_resource=params.get("resource", ""),
            scope=params.get("scope", ""),
            state=params.get("state", ""),
            code_challenge=params.get("code_challenge", ""),
            code_challenge_method=params.get("code_challenge_method", ""),
            response_type=params.get("response_type", ""),
        )
        company_name, storefront_name = await ConnectorAuthService.consent_labels(
            session, pending
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            return HTMLResponse(
                '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Подключить Kitlane</title><h1>Войдите в Kitlane</h1><p>Откройте Manager и войдите в свою учётную запись. Затем вернитесь на эту страницу и обновите её.</p><a href="/manager/" target="_blank" rel="noopener">Открыть Manager</a></html>',
                status_code=401,
                headers=HTML_HEADERS,
            )
        raise
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
    labels = {
        "kitlane:read": "Читать доступные вам данные Kitlane",
        "kitlane:incoming:write": "Сохранять входящие обращения",
        "kitlane:tasks:write": "Создавать и завершать поручения",
    }
    capabilities = "".join(
        f"<li>{html.escape(labels[scope])}</li>" for scope in pending.scopes
    )
    content = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Подключить Kitlane</title><body><h1>Подключить Kitlane к ChatGPT</h1><p>Пользователь: {html.escape(auth.display_name or auth.username)}.</p><p>Компания: {html.escape(company_name)}. Витрина: {html.escape(storefront_name)}.</p><ul>{capabilities}</ul><p>Доступ действует 30 дней. Отозвать его можно в Manager.</p><form method="post" action="/api/connector/oauth/authorize"><input type="hidden" name="consent_id" value="{html.escape(pending.id, quote=True)}"><input type="hidden" name="csrf_token" value="{html.escape(nonce, quote=True)}"><button name="decision" value="allow">Подключить</button> <button name="decision" value="deny">Отмена</button></form></body></html>'''
    response = HTMLResponse(content, headers=HTML_HEADERS)
    response.set_cookie(
        CONSENT_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/connector/oauth/authorize",
    )
    return response


@router.post("/api/connector/oauth/authorize", operation_id="connector_oauth_consent")
async def consent(
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        form = await _form(request)
        nonce = form.get("csrf_token", "")
        if not nonce or not hmac.compare_digest(
            nonce, request.cookies.get(CONSENT_COOKIE, "")
        ):
            raise ConnectorAuthError("invalid_request", "Consent CSRF mismatch", 403)
        if form.get("decision") not in {"allow", "deny"}:
            raise ConnectorAuthError(
                "invalid_request", "Explicit consent decision required"
            )
        url = await ConnectorAuthService.finish_consent(
            session,
            auth,
            _credential(request),
            consent_id=form.get("consent_id", ""),
            nonce=nonce,
            allow=form["decision"] == "allow",
        )
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
    response = RedirectResponse(url, status_code=303, headers=NO_CACHE)
    response.delete_cookie(
        CONSENT_COOKIE,
        path="/api/connector/oauth/authorize",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post(
    "/api/connector/oauth/token",
    operation_id="connector_oauth_token",
    response_model=ConnectorTokenResponse,
)
async def token(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        form = await _form(request)
        if request.headers.get("authorization") or form.get("client_secret"):
            raise ConnectorAuthError(
                "invalid_client", "Public client uses no secret", 401
            )
        if form.get("grant_type") == "authorization_code":
            result = await ConnectorAuthService.exchange_code(
                session,
                code=form.get("code", ""),
                client_id=form.get("client_id", ""),
                redirect_uri=form.get("redirect_uri", ""),
                requested_resource=form.get("resource", ""),
                code_verifier=form.get("code_verifier", ""),
            )
        elif form.get("grant_type") == "refresh_token":
            result = await ConnectorAuthService.refresh(
                session,
                refresh_token=form.get("refresh_token", ""),
                client_id=form.get("client_id", ""),
                requested_resource=form.get("resource", ""),
                scope=form.get("scope"),
            )
        else:
            raise ConnectorAuthError(
                "unsupported_grant_type",
                "Supported grants: authorization_code, refresh_token",
            )
        return JSONResponse(result.model_dump(), headers=NO_CACHE)
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)


@router.post("/api/connector/oauth/revoke", operation_id="connector_oauth_revoke")
async def revoke(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        form = await _form(request)
        await ConnectorAuthService.revoke_token(
            session, token=form.get("token", ""), client_id=form.get("client_id", "")
        )
        return Response(status_code=200, headers=NO_CACHE)
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)


@router.get(
    "/api/manager/connector/grants",
    operation_id=operation_ids.MANAGER_CONNECTOR_GRANTS,
    response_model=ConnectorGrantListResponse,
)
async def grants(
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        items = await ConnectorAuthService.list_grants(session, auth)
        return JSONResponse(
            ConnectorGrantListResponse(
                items=items, csrf_token=csrf_token(_credential(request))
            ).model_dump(mode="json"),
            headers=NO_CACHE,
        )
    except ConnectorAuthError as exc:
        return _error(exc)


@router.post(
    "/api/manager/connector/grants/{grant_id}/revoke",
    operation_id=operation_ids.MANAGER_CONNECTOR_REVOKE,
)
async def manager_revoke(
    grant_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        validate_csrf(request.headers.get("X-CSRF-Token", ""), _credential(request))
        await ConnectorAuthService.revoke_grant(session, auth, grant_id)
        return Response(status_code=204, headers=NO_CACHE)
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
