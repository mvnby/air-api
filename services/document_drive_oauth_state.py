from __future__ import annotations

import secrets
import time
from typing import Any

from core.security import AuthenticatedUser


DOCUMENT_DRIVE_OAUTH_SESSION_KEY = "manager_document_drive_oauth_pending"
DOCUMENT_DRIVE_OAUTH_STATE_TTL_SECONDS = 10 * 60


def start_document_drive_oauth_state(
    request,
    *,
    auth: AuthenticatedUser,
    redirect_uri: str,
) -> str:
    state = secrets.token_urlsafe(32)
    scope = auth.tenant_scope()
    request.session[DOCUMENT_DRIVE_OAUTH_SESSION_KEY] = {
        "state": state,
        "issued_at": time.time(),
        "redirect_uri": redirect_uri,
        "auth_source": auth.auth_source,
        "auth_version": auth.auth_version,
        "staff_user_id": auth.staff_user_id,
        "username": auth.username,
        "tenant_membership_id": auth.tenant_membership_id,
        "tenant_id": scope.tenant_id,
        "storefront_id": scope.storefront_id,
    }
    return state


def consume_document_drive_oauth_state(
    request,
    received_state: str,
) -> dict[str, Any] | None:
    pending = request.session.get(DOCUMENT_DRIVE_OAUTH_SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    expected = str(pending.get("state") or "")
    received = str(received_state or "")
    try:
        age = time.time() - float(pending.get("issued_at"))
    except (TypeError, ValueError):
        request.session.pop(DOCUMENT_DRIVE_OAUTH_SESSION_KEY, None)
        return None
    if not expected or not received or not secrets.compare_digest(expected, received):
        return None
    if age < 0 or age > DOCUMENT_DRIVE_OAUTH_STATE_TTL_SECONDS:
        request.session.pop(DOCUMENT_DRIVE_OAUTH_SESSION_KEY, None)
        return None
    request.session.pop(DOCUMENT_DRIVE_OAUTH_SESSION_KEY, None)
    return dict(pending)
