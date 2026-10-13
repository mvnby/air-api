"""Configured OAuth callbacks must not broaden or inject the consent CSP."""

import pytest

from routers.connector_auth import _consent_headers
from services.connector_auth_policy import ConnectorAuthError
from routers.connector_consent_pages import consent_page

CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"


def test_consent_screen_escapes_names_and_has_separate_mail_permissions():
    from types import SimpleNamespace
    pending = SimpleNamespace(id='id"injection', scopes=["kitlane:read", "kitlane:mail:drafts:write", "kitlane:mail:send"])
    page = consent_page(user_name="<script>user</script>", company_name="<img src=x>",
                        storefront_name="<b>branch</b>", pending=pending, nonce='nonce"injection')
    assert "<script>" not in page and "<img src=x>" not in page and "<b>branch</b>" not in page
    assert '&lt;img src=x&gt;' in page and 'id&quot;injection' in page
    assert 'name="scope:kitlane:mail:send" value="allow">' in page
    assert "Это не разрешает отправку" in page


def test_callback_query_and_fragment_are_not_interpolated_into_policy():
    headers = _consent_headers(CALLBACK + "?state=private#fragment")
    assert f"form-action 'self' {CALLBACK};" in headers["Content-Security-Policy"]
    assert "private" not in headers["Content-Security-Policy"]
    assert "fragment" not in headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "callback",
    [
        "https://*/callback",
        "https://chatgpt.com:*/callback",
        "https://chatgpt.com:bad/callback",
        "https://chatgpt.com:65536/callback",
        "https://chatgpt.com:/callback",
        "https://chatgpt.com/callback; form-action *",
        "https://chatgpt.com/callback,https://evil.example",
        "https://user:password@chatgpt.com/callback",
        "javascript:alert(1)",
        "https:///callback",
        "https://[broken/callback",
        "\n" + CALLBACK,
        CALLBACK.replace("chatgpt", "chat\t gpt"),
        CALLBACK + "\x7f",
    ],
)
def test_invalid_configured_callback_fails_closed(callback):
    with pytest.raises(ConnectorAuthError) as error:
        _consent_headers(callback)
    assert error.value.error == "server_error"
    assert error.value.status_code == 500
