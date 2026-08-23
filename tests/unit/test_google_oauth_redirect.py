from types import SimpleNamespace

import pytest

from services.google_oauth_redirect import (
    GoogleOAuthRedirectConfigurationError,
    resolve_google_oauth_redirect_uri,
)


def test_production_google_oauth_redirect_is_exact_manager_callback():
    runtime_settings = SimpleNamespace(
        is_production=True,
        MANAGER_BASE_URL="https://api.mvn.by/manager",
        GOOGLE_OAUTH_REDIRECT_URI=(
            "https://api.mvn.by/api/manager/google-auth/callback"
        ),
    )

    assert resolve_google_oauth_redirect_uri(runtime_settings=runtime_settings) == (
        "https://api.mvn.by/api/manager/google-auth/callback"
    )


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "",
        "http://127.0.0.1:8000/api/manager/google-auth/callback",
        "https://api.mvn.by/manager/google-auth/callback",
    ],
)
def test_production_google_oauth_redirect_rejects_missing_or_wrong_origin(
    redirect_uri,
):
    runtime_settings = SimpleNamespace(
        is_production=True,
        MANAGER_BASE_URL="https://api.mvn.by/manager",
        GOOGLE_OAUTH_REDIRECT_URI=redirect_uri,
    )

    with pytest.raises(GoogleOAuthRedirectConfigurationError):
        resolve_google_oauth_redirect_uri(runtime_settings=runtime_settings)


def test_local_google_oauth_redirect_can_follow_request_origin():
    runtime_settings = SimpleNamespace(
        is_production=False,
        GOOGLE_OAUTH_REDIRECT_URI="",
    )

    assert resolve_google_oauth_redirect_uri(
        request_callback_uri="http://test/api/manager/google-auth/callback",
        runtime_settings=runtime_settings,
    ) == "http://test/api/manager/google-auth/callback"
