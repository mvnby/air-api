import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from core.app_http import configure_http
from core.config import settings
from core.database import get_session
from core.tenant_scope import verify_public_storefront_request
from tests.unit.storefront_gateway_test_support import (
    STOREFRONT_HOST,
    configure_signing_settings,
    gateway_app,
    gateway_request,
    signed_headers,
)


@pytest.mark.asyncio
async def test_complete_envelope_above_bounded_buffer_is_413(gateway_app):
    body = b"x" * (1024 * 1024 + 1)

    response = await gateway_request(
        gateway_app,
        "POST",
        content=body,
        headers=signed_headers(body=body),
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Storefront request body is too large"}
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"
    assert gateway_app.state.session_calls == 0
    assert gateway_app.state.validated_endpoint_calls == 0


@pytest.mark.asyncio
async def test_unsigned_content_length_overflow_is_413_before_parser(gateway_app):
    body = b"x" * (1024 * 1024 + 1)

    response = await gateway_request(
        gateway_app,
        "POST",
        "/api/v1/validated",
        content=body,
        headers={"Host": "api.mvn.by", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert gateway_app.state.session_calls == 0
    assert gateway_app.state.validated_endpoint_calls == 0


@pytest.mark.asyncio
async def test_unsigned_chunked_overflow_is_413_before_parser(gateway_app):
    chunks = [b"x" * (700 * 1024), b"y" * (400 * 1024)]
    messages = [
        {"type": "http.request", "body": chunks[0], "more_body": True},
        {"type": "http.request", "body": chunks[1], "more_body": False},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    await gateway_app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/validated",
            "raw_path": b"/api/v1/validated",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"api.mvn.by"),
                (b"content-type", b"application/json"),
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("api.mvn.by", 443),
        },
        receive,
        send,
    )

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 413
    assert gateway_app.state.session_calls == 0
    assert gateway_app.state.validated_endpoint_calls == 0


@pytest.mark.asyncio
async def test_unsigned_read_keeps_existing_unbuffered_path(gateway_app):
    response = await gateway_request(
        gateway_app,
        "GET",
        headers={
            "Host": "api.mvn.by",
            "Idempotency-Key": "legacy-client-global-header-0001",
        },
    )

    assert response.status_code == 200
    assert response.json()["storefront_id"] == 1


@pytest.mark.asyncio
async def test_valid_envelope_reaches_body_parser_and_keeps_422_private(gateway_app):
    body = b'{"name":'
    headers = signed_headers(body=body, target=b"/api/v1/validated")
    headers["Content-Type"] = "application/json"

    response = await gateway_request(
        gateway_app,
        "POST",
        "/api/v1/validated",
        content=body,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"
    assert gateway_app.state.session_calls == 0
    assert gateway_app.state.validated_endpoint_calls == 0


@pytest.mark.asyncio
async def test_gateway_merges_existing_vary_without_duplicates(gateway_app):
    response = await gateway_request(
        gateway_app,
        "GET",
        "/api/v1/vary",
        headers=signed_headers(method="GET", target=b"/api/v1/vary"),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == (
        "Accept-Encoding, Origin, X-MVN-Storefront-Host"
    )
    raw_header_names = [name.lower() for name, _ in response.headers.raw]
    assert raw_header_names.count(b"cache-control") == 1
    assert raw_header_names.count(b"cdn-cache-control") == 1
    assert raw_header_names.count(b"vary") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "partial_malformed",
        "forged_malformed",
        "duplicate",
        "unknown",
        "partial_oversized",
        "unsigned_wrong_host",
        "unsigned_required",
    ],
)
async def test_untrusted_request_fails_before_parser_or_dependencies(
    gateway_app,
    case,
    monkeypatch,
):
    body = (
        b"x" * (1024 * 1024 + 1)
        if case == "partial_oversized"
        else b'{"name":'
    )
    if case.startswith("partial"):
        headers = {"X-MVN-Storefront-Host": STOREFRONT_HOST}
    elif case == "unsigned_wrong_host":
        headers = {"Host": STOREFRONT_HOST}
    elif case == "unsigned_required":
        monkeypatch.setattr(
            settings,
            "STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS",
            True,
        )
        headers = {"Host": "api.mvn.by"}
    else:
        headers = signed_headers(body=body, target=b"/api/v1/validated")
        if case == "forged_malformed":
            headers["X-MVN-Storefront-Signature"] = "v2=" + "0" * 64
        elif case == "unknown":
            headers["X-MVN-Storefront-Nonce"] = "unsupported"
        elif case == "duplicate":
            headers = list(headers.items())
            headers.append(("X-MVN-Storefront-Host", STOREFRONT_HOST))
    if isinstance(headers, dict):
        headers["Content-Type"] = "application/json"
    else:
        headers.append(("Content-Type", "application/json"))

    response = await gateway_request(
        gateway_app,
        "POST",
        "/api/v1/validated",
        content=body,
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid storefront context"}
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"
    assert gateway_app.state.session_calls == 0
    assert gateway_app.state.validated_endpoint_calls == 0


@pytest.mark.asyncio
async def test_partial_header_on_unknown_route_fails_closed_early(gateway_app):
    response = await gateway_request(
        gateway_app,
        "GET",
        "/api/v1/missing",
        headers={"X-MVN-Storefront-Nonce": "unsupported"},
    )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"


@pytest.mark.asyncio
async def test_route_dependency_never_trusts_raw_headers_without_scope_marker():
    app = FastAPI()
    calls = {"session": 0, "endpoint": 0}

    async def override_session():
        calls["session"] += 1
        yield object()

    app.dependency_overrides[get_session] = override_session

    @app.get(
        "/api/v1/direct",
        dependencies=[Depends(verify_public_storefront_request)],
    )
    async def direct():
        calls["endpoint"] += 1
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="https://api.mvn.by",
    ) as client:
        response = await client.get(
            "/api/v1/direct",
            headers=signed_headers(method="GET", target=b"/api/v1/direct"),
        )

    assert response.status_code == 401
    assert calls == {"session": 0, "endpoint": 0}


@pytest.mark.asyncio
async def test_unhandled_signed_error_is_never_shared_cacheable(monkeypatch):
    app = FastAPI()
    configure_signing_settings(monkeypatch)
    configure_http(app)
    monkeypatch.setattr("core.app_http.logger.error", lambda *_args, **_kwargs: None)

    @app.get("/api/v1/failure")
    async def fail():
        raise RuntimeError("test failure")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="https://api.mvn.by",
    ) as client:
        response = await client.get(
            "/api/v1/failure",
            headers=signed_headers(method="GET", target=b"/api/v1/failure"),
        )

    assert response.status_code == 500
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"


@pytest.mark.asyncio
async def test_unsigned_canonical_cors_preflight_is_unchanged(monkeypatch):
    app = FastAPI()
    configure_signing_settings(monkeypatch)
    configure_http(app)
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="https://api.mvn.by",
    ) as client:
        response = await client.options(
            "/api/v1/products",
            headers={
                "Host": "api.mvn.by",
                "Origin": "https://mvn.by",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://mvn.by"


@pytest.mark.asyncio
async def test_duplicate_signing_header_fails_closed(gateway_app):
    headers = list(signed_headers().items())
    headers.append(("X-MVN-Storefront-Host", STOREFRONT_HOST))

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_api_host_fails_closed(gateway_app):
    headers = list(signed_headers().items())
    headers.append(("Host", "api.mvn.by"))

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_noncanonical_timestamp_fails_closed(gateway_app):
    headers = signed_headers()
    headers["X-MVN-Storefront-Timestamp"] = (
        "0" + headers["X-MVN-Storefront-Timestamp"]
    )

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401
