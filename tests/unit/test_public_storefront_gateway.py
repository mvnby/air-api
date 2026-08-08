import time

import pytest

from core.config import settings
from tests.unit.storefront_gateway_test_support import (
    PREVIOUS_KEY_ID,
    PREVIOUS_SECRET,
    STOREFRONT_HOST,
    gateway_app,
    gateway_request,
    signed_headers,
)


@pytest.mark.asyncio
async def test_valid_signed_request_resolves_exact_storefront_and_preserves_body(
    gateway_app,
):
    body = b'{"name":"Orsha"}'

    response = await gateway_request(
        gateway_app,
        "POST",
        content=body,
        headers=signed_headers(body=body),
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": 1,
        "storefront_id": 2,
        "body": body.decode("utf-8"),
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"


@pytest.mark.asyncio
async def test_signed_gateway_preserves_multipart_body_for_upload_parser(gateway_app):
    boundary = "mvn-signed-upload-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="canary.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "signed upload\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    headers = signed_headers(
        body=body,
        target=b"/api/v1/upload",
    )
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    response = await gateway_request(
        gateway_app,
        "POST",
        "/api/v1/upload",
        content=body,
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "storefront_id": 2,
        "filename": "canary.txt",
        "content": "signed upload",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "signature",
        "stale",
        "method",
        "path",
        "query",
        "body",
        "api_host",
        "idempotency_key",
    ],
)
async def test_forged_or_tampered_envelope_fails_closed(gateway_app, case):
    body = b'{"name":"Orsha"}'
    method = "POST"
    target = b"/api/v1/echo"
    api_hostname = "api.mvn.by"
    timestamp = int(time.time())

    if case == "stale":
        timestamp -= settings.STOREFRONT_CONTEXT_MAX_AGE_SECONDS + 1
    if case == "method":
        method = "GET"
    if case == "path":
        target = b"/api/v1/other"
    if case == "query":
        target = b"/api/v1/echo?city=orsha"
    headers = signed_headers(
        body=body,
        method=method,
        target=target,
        api_hostname=api_hostname,
        timestamp=timestamp,
    )
    request_body = b'{"name":"Minsk"}' if case == "body" else body
    if case == "api_host":
        headers["Host"] = "localhost"
    if case == "signature":
        headers["X-MVN-Storefront-Signature"] = "v2=" + "0" * 64
    if case == "idempotency_key":
        headers["Idempotency-Key"] = "gateway-request-tampered-0002"

    response = await gateway_request(
        gateway_app,
        "POST",
        content=request_body,
        headers=headers,
    )

    assert response.status_code == 401
    assert gateway_app.state.session_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing", "duplicate", "combined", "whitespace"])
async def test_signed_write_rejects_ambiguous_idempotency_key(gateway_app, case):
    headers = signed_headers()
    if case == "missing":
        headers.pop("Idempotency-Key")
    elif case == "duplicate":
        headers = list(headers.items())
        headers.append(("Idempotency-Key", "gateway-request-duplicate-0002"))
    elif case == "combined":
        headers["Idempotency-Key"] = (
            "gateway-request-0001,gateway-request-duplicate-0002"
        )
    else:
        headers["Idempotency-Key"] = " gateway-request-0001"

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401
    assert gateway_app.state.session_calls == 0


@pytest.mark.asyncio
async def test_signed_read_uses_empty_idempotency_binding(gateway_app):
    response = await gateway_request(
        gateway_app,
        "GET",
        headers=signed_headers(method="GET"),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_signed_read_rejects_smuggled_idempotency_key(gateway_app):
    response = await gateway_request(
        gateway_app,
        "GET",
        headers=signed_headers(
            method="GET",
            idempotency_key="gateway-read-smuggled-0001",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_v1_read_is_rejected_by_default_and_allowed_by_flag(
    gateway_app,
    monkeypatch,
):
    headers = signed_headers(method="GET", signature_version="v1")

    rejected = await gateway_request(gateway_app, "GET", headers=headers)
    assert rejected.status_code == 401

    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS",
        True,
    )
    accepted = await gateway_request(gateway_app, "GET", headers=headers)
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_legacy_v1_write_is_rejected_even_with_read_rollback_flag(
    gateway_app,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS",
        True,
    )
    headers = signed_headers()
    v2_signature = headers["X-MVN-Storefront-Signature"]
    headers["X-MVN-Storefront-Signature"] = (
        "v1=" + v2_signature.split("=", 1)[1]
    )

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401
    assert gateway_app.state.session_calls == 0


@pytest.mark.asyncio
async def test_raw_query_is_part_of_the_signed_target(gateway_app):
    headers = signed_headers(
        method="GET",
        target=b"/api/v1/echo?brand=midea&q=a%2Fb",
    )

    response = await gateway_request(
        gateway_app,
        "GET",
        "/api/v1/echo?brand=midea&q=a%2Fb",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["storefront_id"] == 2


@pytest.mark.asyncio
async def test_raw_percent_encoded_path_is_part_of_signed_target(gateway_app):
    headers = signed_headers(
        method="GET",
        target=b"/api/v1/path/a%2Fb",
    )

    response = await gateway_request(
        gateway_app,
        "GET",
        "/api/v1/path/a%2Fb",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"value": "a/b"}


@pytest.mark.asyncio
async def test_unknown_key_id_fails_without_trying_other_keys(gateway_app):
    headers = signed_headers(key_id="unknown-runtime")

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_previous_key_pair_is_accepted_during_rotation(
    gateway_app,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
        PREVIOUS_KEY_ID,
    )
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        PREVIOUS_SECRET,
    )
    headers = signed_headers(
        key_id=PREVIOUS_KEY_ID,
        secret=PREVIOUS_SECRET,
    )

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 200
    assert response.json()["storefront_id"] == 2


@pytest.mark.asyncio
async def test_clearing_primary_pair_disables_stale_previous_key(
    gateway_app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
        PREVIOUS_KEY_ID,
    )
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        PREVIOUS_SECRET,
    )

    response = await gateway_request(
        gateway_app,
        "POST",
        headers=signed_headers(
            key_id=PREVIOUS_KEY_ID,
            secret=PREVIOUS_SECRET,
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_signature_for_unknown_or_inactive_domain_is_safe_404(
    gateway_app,
):
    headers = signed_headers(storefront_hostname="disabled.mvn.by")

    response = await gateway_request(gateway_app, "POST", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Storefront is unavailable"}
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_unsigned_ordinary_api_host_keeps_canonical_main_scope(gateway_app):
    response = await gateway_request(
        gateway_app,
        "POST",
        headers={
            "Host": "api.mvn.by",
            "Origin": "https://orsha.internal.mvn.by",
            "X-Forwarded-Host": "orsha.internal.mvn.by",
        },
    )

    assert response.status_code == 200
    assert response.json()["storefront_id"] == 1


@pytest.mark.asyncio
async def test_unsigned_non_api_host_is_rejected_instead_of_switching_scope(
    gateway_app,
):
    response = await gateway_request(
        gateway_app,
        "POST",
        headers={"Host": STOREFRONT_HOST},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_require_signed_switch_rejects_unsigned_canonical_request(
    gateway_app,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS",
        True,
    )

    response = await gateway_request(
        gateway_app,
        "POST",
        headers={"Host": "api.mvn.by"},
    )

    assert response.status_code == 401
