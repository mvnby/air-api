"""OAuth security policy vectors, independent of the database."""

import pytest

from core.config import settings
from services.connector_auth_policy import (
    CLIENT_ID,
    ConnectorAuthError,
    csrf_token,
    issuer,
    pkce,
    resource,
    validate_client,
    validate_csrf,
    validate_redirect,
)


def test_pkce_rfc7636_s256_vector():
    assert (
        pkce("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_csrf_bound_to_existing_manager_session():
    token = csrf_token("session-one")
    validate_csrf(token, "session-one")
    with pytest.raises(ConnectorAuthError):
        validate_csrf(token, "session-two")
    with pytest.raises(ConnectorAuthError):
        validate_csrf(token + "bad", "session-one")


def test_csrf_expiry(monkeypatch):
    import services.connector_auth_policy as policy

    monkeypatch.setattr(policy.time, "time", lambda: 1000)
    token = csrf_token("session")
    monkeypatch.setattr(policy.time, "time", lambda: 1601)
    with pytest.raises(ConnectorAuthError):
        validate_csrf(token, "session")


@pytest.mark.parametrize("value", ["", "123.nonce.bad", "not-a-token", "a.b.c"])
def test_invalid_csrf_fails_closed(value):
    with pytest.raises(ConnectorAuthError):
        validate_csrf(value, "session")


@pytest.mark.parametrize(
    "value",
    [
        "http://api.mvn.by",
        "https://api.mvn.by/path",
        "https://user:pass@api.mvn.by",
        "https://api.mvn.by?next=evil",
        "https://api.mvn.by#fragment",
    ],
)
def test_invalid_public_issuer_fails_closed(monkeypatch, value):
    monkeypatch.setattr(settings, "CONNECTOR_PUBLIC_BASE_URL", value)
    with pytest.raises(ConnectorAuthError):
        issuer()


def test_predefined_client_resource_and_exact_redirect():
    validate_client(CLIENT_ID, resource())
    validate_redirect("https://chatgpt.com/connector_platform_oauth_redirect")
    for target in (
        "https://chatgpt.com/connector_platform_oauth_redirect/",
        "https://chatgpt.com/connector_platform_oauth_redirect?next=evil",
        "https://evil.example",
    ):
        with pytest.raises(ConnectorAuthError):
            validate_redirect(target)
    with pytest.raises(ConnectorAuthError):
        validate_client("https://evil.example/client.json", resource())
    with pytest.raises(ConnectorAuthError):
        validate_client(CLIENT_ID, resource() + "/other")
