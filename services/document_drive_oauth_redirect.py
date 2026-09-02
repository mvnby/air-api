from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from core.config import settings
from services.google_oauth_redirect import GoogleOAuthRedirectConfigurationError


DOCUMENT_DRIVE_OAUTH_CALLBACK_PATH = "/api/manager/google-auth/callback"
LOCAL_DOCUMENT_DRIVE_OAUTH_REDIRECT_URI = (
    f"http://127.0.0.1:8000{DOCUMENT_DRIVE_OAUTH_CALLBACK_PATH}"
)


def resolve_document_drive_oauth_redirect_uri(
    *,
    request_callback_uri: str | None = None,
    runtime_settings=None,
) -> str:
    active_settings = runtime_settings or settings
    configured = str(
        getattr(active_settings, "GOOGLE_DOCUMENT_DRIVE_OAUTH_REDIRECT_URI", "")
    ).strip()
    if not active_settings.is_production:
        return configured or request_callback_uri or LOCAL_DOCUMENT_DRIVE_OAUTH_REDIRECT_URI

    manager = urlsplit(str(active_settings.MANAGER_BASE_URL).strip())
    canonical = urlunsplit(
        (manager.scheme, manager.netloc, DOCUMENT_DRIVE_OAUTH_CALLBACK_PATH, "", "")
    )
    if manager.scheme != "https" or not manager.hostname:
        raise GoogleOAuthRedirectConfigurationError(
            "Document Drive OAuth redirect URI is not configured for the manager origin"
        )
    if configured and configured != canonical:
        raise GoogleOAuthRedirectConfigurationError(
            "Document Drive OAuth redirect URI is not configured for the manager origin"
        )
    return canonical
