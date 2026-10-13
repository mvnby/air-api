"""OAuth HTTP adapter and an explicit Manager-authenticated consent screen."""

from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.connector_security import connector_resource_metadata
from core.security import (
    AuthenticatedUser,
    get_current_auth_context,
    require_manager_access,
)
from routers import manager_operation_ids as operation_ids
from routers.connector_consent_pages import consent_page
from schemas_connector_auth import ConnectorGrantListResponse, ConnectorTokenResponse
from services.connector_auth_policy import (
    SCOPES,
    ConnectorAuthError,
    csrf_token,
    issuer,
    validate_csrf,
    validate_authorization_request,
)
from services.connector_auth_service import ConnectorAuthService

router = APIRouter(tags=["connector-auth"])
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


def _consent_headers(redirect_uri: str) -> dict[str, str]:
    # Only the exact registered redirect from durable consent may reach here.
    # Chromium also applies form-action to the POST's cross-origin redirect.
    try:
        # urlsplit strips some controls, so validate the original value too.
        if any(
            ord(character) <= 32 or ord(character) == 127 for character in redirect_uri
        ):
            raise ValueError
        parsed = urlsplit(redirect_uri)
        callback = parsed._replace(query="", fragment="").geturl()
        _ = parsed.port  # Reject malformed or out-of-range configured ports.
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.netloc.endswith(":")
            or any(
                character.isspace() or character in ";'\"*," for character in callback
            )
        ):
            raise ValueError
    except ValueError:
        raise ConnectorAuthError(
            "server_error", "Invalid configured callback", 500
        ) from None
    return {
        **HTML_HEADERS,
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; "
            f"form-action 'self' {callback}; frame-ancestors 'none'"
        ),
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


def _manager_login_redirect(request: Request) -> RedirectResponse:
    target = "/api/connector/oauth/authorize?" + str(request.query_params)
    return RedirectResponse(
        "/manager/?" + urlencode({"connector_return": target}),
        status_code=303, headers=NO_CACHE,
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
    """
    Publish OAuth authorization-server discovery for the configured issuer, supported
    grants/scopes and PKCE S256. No Manager session is required; this does not dynamically
    register clients.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
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
    """
    Publish OAuth protected-resource discovery for the exact MCP resource. Available at both
    well-known paths without a Manager session. OAuth metadata is not the MCP tools catalog.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
    return connector_resource_metadata()


@router.get(
    "/api/connector/oauth/authorize",
    operation_id="connector_oauth_authorize",
    response_class=HTMLResponse,
)
async def authorize(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Start a one-time OAuth consent bound to the current authenticated Manager session and
    render an HTML consent page. Requires the registered client/callback, exact resource,
    scopes and PKCE S256; duplicate query parameters are rejected. A valid request without
    a usable personal session redirects to Manager and resumes after sign-in or password
    change. Legacy shared accounts must use a named login. OAuth errors use
    error/error_description and no-store headers. Company is resolved from live membership.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
    try:
        # Reject parameter pollution before any state or consent is created.
        params = request.query_params
        if len(str(params)) > 8192:
            raise ConnectorAuthError("invalid_request", "Authorization request too large")
        if any(len(params.getlist(key)) != 1 for key in params):
            raise ConnectorAuthError(
                "invalid_request", "Duplicate authorization parameters"
            )
        authorization = dict(
            client_id=params.get("client_id", ""),
            redirect_uri=params.get("redirect_uri", ""),
            requested_resource=params.get("resource", ""),
            scope=params.get("scope", ""), state=params.get("state", ""),
            code_challenge=params.get("code_challenge", ""),
            code_challenge_method=params.get("code_challenge_method", ""),
            response_type=params.get("response_type", ""),
        )
        validate_authorization_request(**authorization)
        auth = await get_current_auth_context(request, token=None, session=session)
        auth = await require_manager_access(auth)
        if not auth.staff_user_id or auth.auth_source == "legacy" or auth.must_change_password:
            return _manager_login_redirect(request)
        pending, nonce = await ConnectorAuthService.start_consent(
            session,
            auth,
            _credential(request),
            **authorization,
        )
        company_name, storefront_name = await ConnectorAuthService.consent_labels(
            session, pending
        )
        headers = _consent_headers(pending.redirect_uri)
    except HTTPException as exc:
        if exc.status_code == 401:
            return _manager_login_redirect(request)
        raise
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
    content = consent_page(user_name=auth.display_name or auth.username,
                           company_name=company_name, storefront_name=storefront_name,
                           pending=pending, nonce=nonce)
    return HTMLResponse(content, headers=headers)


@router.post("/api/connector/oauth/authorize", operation_id="connector_oauth_consent")
async def consent(
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    Finish the durable consent using explicit allow/deny, consent_id and its one-time CSRF
    token bound to the same live Manager session. scope_selection=explicit and
    scope:<name>=allow fields select a subset of requested permissions; cannot expand them.
    An allow form without an explicit selection grants only the mandatory kitlane:read.
    Accepts application/x-www-form-urlencoded
    up to 8192 bytes; duplicate parameters are rejected. Success redirects with 303 to the
    registered callback; OAuth errors use error/error_description. Do not blindly replay a
    consumed consent.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
    try:
        form = await _form(request)
        nonce = form.get("csrf_token", "")
        if form.get("decision") not in {"allow", "deny"}:
            raise ConnectorAuthError(
                "invalid_request", "Explicit consent decision required"
            )
        # The one-time synchronizer token is validated against durable consent,
        # its Manager session and live actor. A shared cookie would let another
        # open consent page replace this page's nonce.
        selected_scopes = ["kitlane:read"]
        if "scope_selection" in form:
            if form["scope_selection"] != "explicit":
                raise ConnectorAuthError("invalid_request", "Unknown scope selection")
            for key, value in form.items():
                if key.startswith("scope:"):
                    scope = key[len("scope:"):]
                    if scope not in SCOPES or value != "allow":
                        raise ConnectorAuthError("invalid_scope", "Unknown permission")
                    selected_scopes.append(scope)
        url = await ConnectorAuthService.finish_consent(
            session,
            auth,
            _credential(request),
            consent_id=form.get("consent_id", ""),
            nonce=nonce,
            allow=form["decision"] == "allow",
            selected_scopes=selected_scopes,
        )
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
    return RedirectResponse(url, status_code=303, headers=NO_CACHE)


@router.post(
    "/api/connector/oauth/token",
    operation_id="connector_oauth_token",
    response_model=ConnectorTokenResponse,
)
async def token(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Exchange an authorization code with PKCE or rotate a refresh token for the registered
    public client and exact MCP resource. Accepts application/x-www-form-urlencoded up to
    8192 bytes; duplicate fields, Authorization/client_secret and unsupported grants are
    rejected. No Manager JWT is used here. Refresh reuse revokes the grant; after losing a
    refresh response do not treat the old token as safely replayable. OAuth errors use
    error/error_description; responses are no-store.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
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
    """
    Revoke a connector access/refresh token using its registered client_id. Accepts
    application/x-www-form-urlencoded up to 8192 bytes; duplicate fields are rejected.
    Success has an empty 200 body and no-store headers. No Manager JWT is used for this
    token endpoint; errors use OAuth error/error_description.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
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
    """
    List OAuth grants belonging to the current authenticated Manager actor and return a
    session-bound CSRF token for profile revocation. Response is no-store; does not list
    other users’ grants. Includes active, revoked and expired grants, creation time and
    nullable last authenticated MCP use (recorded at most once per minute). Listing the
    profile does not count as use and never revokes or replaces grants.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
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
    """
    Revoke the current Manager actor’s grant using X-CSRF-Token bound to that Manager
    credential. Requires live Manager access and grant ownership; success is 204 with no
    body/no-store headers. OAuth policy errors use error/error_description. Removing a
    client plugin alone does not invoke this revocation.

    See [connector access and
    scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
    MCP transport and tools/list are outside this HTTP schema.
    """
    try:
        validate_csrf(request.headers.get("X-CSRF-Token", ""), _credential(request))
        await ConnectorAuthService.revoke_grant(session, auth, grant_id)
        return Response(status_code=204, headers=NO_CACHE)
    except ConnectorAuthError as exc:
        await session.rollback()
        return _error(exc)
