from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from core.config import settings


GOOGLE_OAUTH_CALLBACK_PATH = "/api/manager/google-auth/callback"
LOCAL_GOOGLE_OAUTH_REDIRECT_URI = (
    f"http://127.0.0.1:8000{GOOGLE_OAUTH_CALLBACK_PATH}"
)


class GoogleOAuthRedirectConfigurationError(RuntimeError):
    pass


def resolve_google_oauth_redirect_uri(
    *,
    request_callback_uri: str | None = None,
    runtime_settings=None,
) -> str:
    active_settings = runtime_settings or settings
    configured = str(
        getattr(active_settings, "GOOGLE_OAUTH_REDIRECT_URI")
        if hasattr(active_settings, "GOOGLE_OAUTH_REDIRECT_URI")
        else os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    ).strip()
    if not active_settings.is_production:
        return configured or request_callback_uri or LOCAL_GOOGLE_OAUTH_REDIRECT_URI

    manager = urlsplit(
        str(getattr(active_settings, "MANAGER_BASE_URL", "https://api.mvn.by/manager")).strip()
    )
    canonical = urlunsplit((manager.scheme, manager.netloc, GOOGLE_OAUTH_CALLBACK_PATH, "", ""))
    if not configured or configured != canonical or manager.scheme != "https" or not manager.hostname:
        raise GoogleOAuthRedirectConfigurationError(
            "Google OAuth redirect URI is not configured for the production manager origin"
        )
    return canonical
