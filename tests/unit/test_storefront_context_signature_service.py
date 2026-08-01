import pytest

from services.storefront_context_signature_service import (
    InvalidStorefrontContextSignature,
    StorefrontContextSignatureService,
)


_SECRET = "test-storefront-secret-at-least-32-bytes"


def _signature(*, timestamp: int = 1_700_000_000) -> str:
    return StorefrontContextSignatureService.sign(
        secret=_SECRET,
        timestamp=timestamp,
        method="POST",
        path="/api/v1/leads/contact",
        hostname="CITY.MVN.BY:443",
    )


def test_signature_round_trip_returns_normalized_hostname():
    signature = _signature()

    hostname = StorefrontContextSignatureService.verify(
        secret=_SECRET,
        timestamp=1_700_000_000,
        method="post",
        path="/api/v1/leads/contact",
        hostname="city.mvn.by",
        signature=signature,
        max_age_seconds=300,
        now=1_700_000_100,
    )

    assert hostname == "city.mvn.by"
    assert signature.startswith("v1=")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("method", "GET"),
        ("path", "/api/v1/orders"),
        ("hostname", "other.mvn.by"),
        ("signature", "v1=" + "0" * 64),
    ],
)
def test_signature_rejects_tampered_request_target(field, value):
    kwargs = {
        "secret": _SECRET,
        "timestamp": 1_700_000_000,
        "method": "POST",
        "path": "/api/v1/leads/contact",
        "hostname": "city.mvn.by",
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


def test_signature_rejects_expired_timestamp():
    with pytest.raises(
        InvalidStorefrontContextSignature,
        match="has expired",
    ):
        StorefrontContextSignatureService.verify(
            secret=_SECRET,
            timestamp=1_700_000_000,
            method="POST",
            path="/api/v1/leads/contact",
            hostname="city.mvn.by",
            signature=_signature(),
            max_age_seconds=300,
            now=1_700_000_301,
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
            path="/api/v1/leads/contact",
            hostname="city.mvn.by",
        )


def test_verify_any_accepts_previous_secret_during_rotation():
    signature = StorefrontContextSignatureService.sign(
        secret=_SECRET,
        timestamp=1_700_000_000,
        method="POST",
        path="/api/v1/leads/contact",
        hostname="city.mvn.by",
    )

    hostname = StorefrontContextSignatureService.verify_any(
        secrets=("new-storefront-secret-at-least-32-bytes", _SECRET),
        timestamp=1_700_000_000,
        method="POST",
        path="/api/v1/leads/contact",
        hostname="city.mvn.by",
        signature=signature,
        max_age_seconds=300,
        now=1_700_000_100,
    )

    assert hostname == "city.mvn.by"
