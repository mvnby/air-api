from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from core.config import settings
from core.database import get_session
from core.public_write_key import public_write_idempotency_key_sha256
from core.storefront_request_gateway import StorefrontRequestGatewayMiddleware
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from models.tenancy import TenantScope
from services.storefront_context_service import (
    StorefrontContext,
    StorefrontContextService,
)
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)
from services.tenant_scope_service import SystemTenantScopeResolver


PRIMARY_KEY_ID = "mvn-web-current"
PRIMARY_SECRET = "primary-storefront-secret-at-least-32-bytes"
PREVIOUS_KEY_ID = "mvn-web-previous"
PREVIOUS_SECRET = "previous-storefront-secret-at-least-32-bytes"
STOREFRONT_HOST = "orsha.internal.mvn.by"
DEFAULT_IDEMPOTENCY_KEY = "gateway-request-0001"
_DEFAULT_KEY = object()


class ValidatedPayload(BaseModel):
    name: str


def signed_headers(
    *,
    body: bytes = b"",
    method: str = "POST",
    target: bytes = b"/api/v1/echo",
    api_hostname: str = "api.mvn.by",
    storefront_hostname: str = STOREFRONT_HOST,
    key_id: str = PRIMARY_KEY_ID,
    secret: str = PRIMARY_SECRET,
    timestamp: int | None = None,
    idempotency_key: str | None | object = _DEFAULT_KEY,
) -> dict[str, str]:
    signed_at = int(time.time()) if timestamp is None else timestamp
    normalized_method = method.upper()
    if idempotency_key is _DEFAULT_KEY:
        idempotency_key = (
            None
            if normalized_method in {"GET", "HEAD", "OPTIONS"}
            else DEFAULT_IDEMPOTENCY_KEY
        )
    idempotency_digest = (
        public_write_idempotency_key_sha256(idempotency_key)
        if isinstance(idempotency_key, str) and idempotency_key
        else ""
    )
    headers = {
        "Host": api_hostname,
        "X-MVN-Storefront-Key-Id": key_id,
        "X-MVN-Storefront-Host": storefront_hostname,
        "X-MVN-Storefront-Timestamp": str(signed_at),
        "X-MVN-Storefront-Signature": StorefrontContextSignatureService.sign(
            secret=secret,
            timestamp=signed_at,
            method=method,
            path_and_query=target,
            api_hostname=api_hostname,
            storefront_hostname=storefront_hostname,
            body_sha256=StorefrontContextSignatureService.body_sha256(body),
            idempotency_key_sha256=idempotency_digest,
        ),
    }
    if isinstance(idempotency_key, str) and idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def configure_signing_settings(monkeypatch) -> None:
    values = {
        "STOREFRONT_CONTEXT_SIGNING_KEY_ID": PRIMARY_KEY_ID,
        "STOREFRONT_CONTEXT_SIGNING_SECRET": PRIMARY_SECRET,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID": "",
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET": "",
        "STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS": False,
        "STOREFRONT_CONTEXT_API_HOSTS": "api.mvn.by,localhost",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def gateway_app(monkeypatch):
    app = FastAPI()
    app.add_middleware(
        StorefrontRequestGatewayMiddleware,
        max_body_bytes=1024 * 1024,
    )
    app.state.session_calls = 0
    app.state.validated_endpoint_calls = 0
    canonical_scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    orsha_context = StorefrontContext(
        tenant_id=1,
        tenant_slug="mvn",
        tenant_kind="operator",
        storefront_id=2,
        storefront_slug="orsha",
        storefront_name="MVN Орша",
        hostname=STOREFRONT_HOST,
        city="Орша",
        default_locale="ru-BY",
        currency="BYN",
        tenant_is_system=True,
    )

    async def override_session():
        app.state.session_calls += 1
        yield object()

    async def resolve_system(_session, **_kwargs):
        return canonical_scope

    async def resolve_storefront(_session, raw_host):
        if raw_host == STOREFRONT_HOST:
            return orsha_context
        return None

    monkeypatch.setattr(SystemTenantScopeResolver, "resolve", resolve_system)
    monkeypatch.setattr(
        StorefrontContextService,
        "resolve_by_host",
        resolve_storefront,
    )
    configure_signing_settings(monkeypatch)
    app.dependency_overrides[get_session] = override_session

    @app.api_route(
        "/api/v1/echo",
        methods=["GET", "POST"],
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def echo(
        request: Request,
        tenant_scope: TenantScope = Depends(get_public_tenant_scope),
    ):
        return {
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "body": (await request.body()).decode("utf-8"),
        }

    @app.post(
        "/api/v1/upload",
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def upload(
        file: UploadFile = File(),
        tenant_scope: TenantScope = Depends(get_public_tenant_scope),
    ):
        return {
            "storefront_id": tenant_scope.storefront_id,
            "filename": file.filename,
            "content": (await file.read()).decode("utf-8"),
        }

    @app.post(
        "/api/v1/validated",
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def validated(payload: ValidatedPayload):
        app.state.validated_endpoint_calls += 1
        return payload

    @app.get(
        "/api/v1/vary",
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def response_with_existing_vary():
        return JSONResponse(
            content={"ok": True},
            headers={
                "Cache-Control": "public, max-age=3600",
                "CDN-Cache-Control": "public, max-age=3600",
                "Vary": "Accept-Encoding, Origin, accept-encoding",
            },
        )

    @app.get(
        "/api/v1/path/{value:path}",
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def encoded_path(value: str):
        return {"value": value}

    return app


async def gateway_request(
    app: FastAPI,
    method: str,
    path: str = "/api/v1/echo",
    **kwargs,
):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="https://api.mvn.by",
    ) as client:
        return await client.request(method, path, **kwargs)
