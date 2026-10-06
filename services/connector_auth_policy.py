"""Fixed public-client policy; deliberately no dynamic registration or URL fetch."""

import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from core.config import settings

CLIENT_ID = "kitlane-chatgpt"
SCOPES = frozenset({"kitlane:read", "kitlane:incoming:write", "kitlane:tasks:write"})
ROLE_RANK = {"manager": 1, "admin": 2, "owner": 3}
VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class ConnectorAuthError(ValueError):
    def __init__(self, error: str, description: str, status_code: int = 400):
        super().__init__(description)
        self.error = error
        self.status_code = status_code


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secret(kind: str) -> str:
    return f"kl_{kind}_" + secrets.token_urlsafe(32)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def issuer() -> str:
    base = str(
        getattr(settings, "CONNECTOR_PUBLIC_BASE_URL", "https://api.mvn.by")
    ).rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.path
    ):
        raise ConnectorAuthError(
            "server_error", "Invalid connector public base URL", 500
        )
    return base


def resource() -> str:
    return issuer() + "/api/connector/mcp"


def validate_client(client_id: str, requested_resource: str) -> None:
    if client_id != CLIENT_ID:
        raise ConnectorAuthError("invalid_client", "Unknown OAuth client", 401)
    if requested_resource != resource():
        raise ConnectorAuthError(
            "invalid_target", "Connector resource must match exactly"
        )


def validate_redirect(redirect_uri: str) -> None:
    allowed = getattr(
        settings,
        "CONNECTOR_REDIRECT_URIS",
        ["https://chatgpt.com/connector_platform_oauth_redirect"],
    )
    if redirect_uri not in allowed:
        raise ConnectorAuthError("invalid_request", "Redirect URI is not registered")


def csrf_token(session_credential: str) -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(24)}"
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        f"{digest(session_credential)}:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return payload + "." + signature


def validate_csrf(value: str, session_credential: str) -> None:
    try:
        timestamp, nonce, signature = value.split(".")
        age = time.time() - int(timestamp)
        payload = timestamp + "." + nonce
    except (ValueError, TypeError):
        raise ConnectorAuthError("invalid_request", "Invalid CSRF token", 403) from None
    expected = hmac.new(
        settings.SECRET_KEY.encode(),
        f"{digest(session_credential)}:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not 0 <= age <= 600 or not hmac.compare_digest(signature, expected):
        raise ConnectorAuthError("invalid_request", "Invalid CSRF token", 403)


def pkce(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
