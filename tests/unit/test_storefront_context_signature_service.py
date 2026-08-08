import pytest

from services.storefront_context_signature_service import (
    InvalidStorefrontContextSignature,
    StorefrontContextSignatureService,
)


_SECRET = "test-storefront-secret-at-least-32-bytes"
_BODY = b'{"name":"Orsha"}'
_BODY_SHA256 = StorefrontContextSignatureService.body_sha256(_BODY)
_IDEMPOTENCY_KEY_SHA256 = "a" * 64


def _signature(*, timestamp: int = 1_700_000_000) -> str:
    return StorefrontContextSignatureService.sign(
        secret=_SECRET,
        timestamp=timestamp,
        method="POST",
        path_and_query=b"/api/v1/leads/contact?source=city%20page&tag=a%2Fb",
        api_hostname="API.MVN.BY:443",
        storefront_hostname="CITY.MVN.BY:443",
        body_sha256=_BODY_SHA256,
        idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
    )


def test_canonical_message_has_exact_v2_field_order_and_no_trailing_newline():
    message = StorefrontContextSignatureService.canonical_message(
        timestamp=1_700_000_000,
        method="post",
        path_and_query=b"/api/v1/leads/contact?b=2&a=%2F",
        api_hostname="API.MVN.BY:443",
        storefront_hostname="CITY.MVN.BY.",
        body_sha256=_BODY_SHA256,
        idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
    )

    assert message == (
        b"v2\n"
        b"1700000000\n"
        b"POST\n"
        b"/api/v1/leads/contact?b=2&a=%2F\n"
        b"api.mvn.by\n"
        b"city.mvn.by\n"
        + _BODY_SHA256.encode("ascii")
        + b"\n"
        + _IDEMPOTENCY_KEY_SHA256.encode("ascii")
    )
    assert not message.endswith(b"\n")


def test_signature_round_trip_returns_normalized_storefront_hostname():
    signature = _signature()

    hostname = StorefrontContextSignatureService.verify(
        secret=_SECRET,
        timestamp=1_700_000_000,
        method="post",
        path_and_query=b"/api/v1/leads/contact?source=city%20page&tag=a%2Fb",
        api_hostname="api.mvn.by",
        storefront_hostname="city.mvn.by",
        body_sha256=_BODY_SHA256,
        idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
        signature=signature,
        max_age_seconds=300,
        now=1_700_000_100,
    )

    assert hostname == "city.mvn.by"
    assert signature.startswith("v2=")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("method", "GET"),
        ("path_and_query", b"/api/v1/leads/contact?tag=a%2fb&source=city%20page"),
        ("api_hostname", "other-api.mvn.by"),
        ("storefront_hostname", "other.mvn.by"),
        ("body_sha256", StorefrontContextSignatureService.body_sha256(b"tampered")),
        ("idempotency_key_sha256", "b" * 64),
        ("signature", "v2=" + "0" * 64),
    ],
)
def test_signature_rejects_tampered_request(field, value):
    kwargs = {
        "secret": _SECRET,
        "timestamp": 1_700_000_000,
        "method": "POST",
        "path_and_query": b"/api/v1/leads/contact?source=city%20page&tag=a%2Fb",
        "api_hostname": "api.mvn.by",
        "storefront_hostname": "city.mvn.by",
        "body_sha256": _BODY_SHA256,
        "idempotency_key_sha256": _IDEMPOTENCY_KEY_SHA256,
        "signature": _signature(),
        "max_age_seconds": 300,
        "now": 1_700_000_100,
    }
    kwargs[field] = value

    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="signature is invalid",
    ):
        StorefrontContextSignatureService.verify(**kwargs)


@pytest.mark.parametrize("now", [1_699_999_699, 1_700_000_301])
def test_signature_rejects_timestamp_outside_past_or_future_window(now):
    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="has expired",
    ):
        StorefrontContextSignatureService.verify(
            secret=_SECRET,
            timestamp=1_700_000_000,
            method="POST",
            path_and_query="/api/v1/leads/contact",
            api_hostname="api.mvn.by",
            storefront_hostname="city.mvn.by",
            body_sha256=_BODY_SHA256,
            idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
            signature=StorefrontContextSignatureService.sign(
                secret=_SECRET,
                timestamp=1_700_000_000,
                method="POST",
                path_and_query="/api/v1/leads/contact",
                api_hostname="api.mvn.by",
                storefront_hostname="city.mvn.by",
                body_sha256=_BODY_SHA256,
                idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
            ),
            max_age_seconds=300,
            now=now,
        )


@pytest.mark.parametrize(
    "signature",
    [
        "",
        "v3=" + "0" * 64,
        "v2=" + "A" * 64,
        "v2=" + "0" * 63,
        "v2=" + "0" * 65,
    ],
)
def test_signature_rejects_noncanonical_signature_format(signature):
    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="signature is invalid",
    ):
        StorefrontContextSignatureService.verify(
            secret=_SECRET,
            timestamp=1_700_000_000,
            method="POST",
            path_and_query="/api/v1/leads/contact",
            api_hostname="api.mvn.by",
            storefront_hostname="city.mvn.by",
            body_sha256=_BODY_SHA256,
            idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
            signature=signature,
            max_age_seconds=300,
            now=1_700_000_100,
        )


def test_request_target_preserves_raw_query_bytes():
    assert StorefrontContextSignatureService.request_target(
        raw_path=b"/api/v1/products",
        query_string=b"brand=midea&brand=gree&q=a%2Fb",
    ) == b"/api/v1/products?brand=midea&brand=gree&q=a%2Fb"


def test_legacy_v1_seven_field_envelope_is_default_off_read_only():
    signature = StorefrontContextSignatureService.sign_legacy_v1_read(
        secret=_SECRET,
        timestamp=1_700_000_000,
        method="GET",
        path_and_query="/api/v1/products?limit=1",
        api_hostname="api.mvn.by",
        storefront_hostname="city.mvn.by",
        body_sha256=StorefrontContextSignatureService.EMPTY_BODY_SHA256,
    )

    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="Legacy storefront signatures are disabled",
    ):
        StorefrontContextSignatureService.verify(
            secret=_SECRET,
            timestamp=1_700_000_000,
            method="GET",
            path_and_query="/api/v1/products?limit=1",
            api_hostname="api.mvn.by",
            storefront_hostname="city.mvn.by",
            body_sha256=StorefrontContextSignatureService.EMPTY_BODY_SHA256,
            idempotency_key_sha256="",
            signature=signature,
            max_age_seconds=300,
            now=1_700_000_100,
        )

    assert StorefrontContextSignatureService.verify(
        secret=_SECRET,
        timestamp=1_700_000_000,
        method="GET",
        path_and_query="/api/v1/products?limit=1",
        api_hostname="api.mvn.by",
        storefront_hostname="city.mvn.by",
        body_sha256=StorefrontContextSignatureService.EMPTY_BODY_SHA256,
        idempotency_key_sha256="",
        signature=signature,
        max_age_seconds=300,
        now=1_700_000_100,
        allow_legacy_v1_read_requests=True,
    ) == "city.mvn.by"


def test_legacy_v1_write_is_rejected_even_when_read_rollback_is_enabled():
    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="read-only",
    ):
        StorefrontContextSignatureService.verify(
            secret=_SECRET,
            timestamp=1_700_000_000,
            method="POST",
            path_and_query="/api/v1/leads/contact",
            api_hostname="api.mvn.by",
            storefront_hostname="city.mvn.by",
            body_sha256=_BODY_SHA256,
            idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
            signature="v1=" + "0" * 64,
            max_age_seconds=300,
            now=1_700_000_100,
            allow_legacy_v1_read_requests=True,
        )


def test_signature_rejects_missing_secret():
    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="not configured securely",
    ):
        StorefrontContextSignatureService.sign(
            secret="",
            timestamp=1_700_000_000,
            method="POST",
            path_and_query="/api/v1/leads/contact",
            api_hostname="api.mvn.by",
            storefront_hostname="city.mvn.by",
            body_sha256=_BODY_SHA256,
            idempotency_key_sha256=_IDEMPOTENCY_KEY_SHA256,
        )
