from types import SimpleNamespace

from core.security import AuthenticatedUser
from services.document_drive_oauth_state import (
    DOCUMENT_DRIVE_OAUTH_SESSION_KEY,
    consume_document_drive_oauth_state,
    start_document_drive_oauth_state,
)


def test_document_drive_oauth_state_preserves_actor_scope_and_is_single_use():
    request = SimpleNamespace(session={})
    auth = AuthenticatedUser(
        username="tenant-owner",
        auth_source="staff_password",
        staff_user_id=5,
        role="owner",
        tenant_id=21,
        storefront_id=71,
        tenant_membership_id=31,
        auth_version=4,
    )
    state = start_document_drive_oauth_state(
        request,
        auth=auth,
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
    )

    assert consume_document_drive_oauth_state(request, "wrong-state") is None
    pending = consume_document_drive_oauth_state(request, state)
    assert pending is not None
    assert pending["tenant_id"] == 21
    assert pending["storefront_id"] == 71
    assert pending["tenant_membership_id"] == 31
    assert pending["staff_user_id"] == 5
    assert pending["auth_version"] == 4
    assert DOCUMENT_DRIVE_OAUTH_SESSION_KEY not in request.session
    assert consume_document_drive_oauth_state(request, state) is None


def test_document_drive_state_preserves_explicit_platform_support_kind():
    request = SimpleNamespace(session={})
    auth = AuthenticatedUser(username="platform-owner", auth_source="staff_password",
        staff_user_id=5, role="owner", tenant_id=21, storefront_id=71,
        tenant_membership_id=None, auth_version=4, is_platform_owner=True,
        access_kind="platform_support")
    state = start_document_drive_oauth_state(request, auth=auth,
        redirect_uri="https://example.test/callback")
    pending = consume_document_drive_oauth_state(request, state)
    assert pending["access_kind"] == "platform_support"
    assert pending["tenant_membership_id"] is None
