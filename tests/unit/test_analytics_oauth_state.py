from types import SimpleNamespace

from core.security import AuthenticatedUser
from services.analytics_oauth_state import (
    ANALYTICS_GOOGLE_OAUTH_SESSION_KEY,
    consume_google_oauth_state,
    start_google_oauth_state,
)


def test_analytics_google_oauth_state_is_scope_bound_and_single_use():
    request = SimpleNamespace(session={})
    auth = AuthenticatedUser(
        username="owner",
        auth_source="staff",
        staff_user_id=5,
        role="owner",
        tenant_id=21,
        storefront_id=71,
        tenant_membership_id=31,
        auth_version=4,
    )

    state = start_google_oauth_state(
        request,
        auth=auth,
        provider="google_analytics",
        public_config={"property_id": "123456"},
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
    )

    assert consume_google_oauth_state(request, "wrong-state") is None
    pending = consume_google_oauth_state(request, state)
    assert pending is not None
    assert pending["tenant_id"] == 21
    assert pending["storefront_id"] == 71
    assert pending["staff_user_id"] == 5
    assert pending["public_config"] == {"property_id": "123456"}
    assert ANALYTICS_GOOGLE_OAUTH_SESSION_KEY not in request.session
    assert consume_google_oauth_state(request, state) is None
