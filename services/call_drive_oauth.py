"""One-use browser state bound to live staff identity and the Manager origin."""

import secrets
import time
from urllib.parse import urlsplit, urlunsplit

from core.command_actor import CommandActor
from core.config import settings
from models import StaffUser
from models.tenancy import TenantScope
from services.call_drive_connection_service import CallDriveConnectionService, require_live_call_actor
from services.call_drive_provider import CallDriveError

SESSION_KEY = "manager_personal_call_drive_oauth_pending"
CALLBACK_PATH = "/api/manager/call-recordings/oauth/callback"


def callback_uri(request) -> str:
    configured = settings.CALL_RECORDINGS_OAUTH_REDIRECT_URI.strip()
    if not settings.is_production:
        return configured or str(request.url_for("manager_call_drive_callback"))
    manager = urlsplit(settings.MANAGER_BASE_URL)
    canonical = urlunsplit((manager.scheme, manager.netloc, CALLBACK_PATH, "", ""))
    if manager.scheme != "https" or not manager.hostname or (configured and configured != canonical):
        raise CallDriveError("call_oauth_not_configured", "Адрес подключения Google не настроен", status_code=503)
    return canonical


def start(request, auth, redirect_uri):
    actor = CommandActor.from_auth(auth)
    state = secrets.token_urlsafe(32)
    request.session[SESSION_KEY] = {"state": state, "issued_at": time.time(), "redirect_uri": redirect_uri, "staff_user_id": actor.staff_user_id, "auth_version": auth.auth_version, "tenant_id": actor.tenant_scope.tenant_id, "storefront_id": actor.tenant_scope.storefront_id, "demo_read_only": auth.demo_read_only}
    return state


def consume(request, state):
    pending = request.session.get(SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    try:
        valid = bool(state) and secrets.compare_digest(str(state), str(pending.get("state") or "")) and 0 <= time.time() - float(pending["issued_at"]) <= 600
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        return None
    return request.session.pop(SESSION_KEY)


async def pending_actor(session, pending):
    try:
        user = await session.get(StaffUser, int(pending["staff_user_id"]), populate_existing=True)
        if user is None or user.auth_version != int(pending["auth_version"]):
            raise PermissionError("Сеанс сотрудника изменился")
        actor = CommandActor(user.id, user.username or str(user.id), TenantScope(int(pending["tenant_id"]), int(pending["storefront_id"]), demo_read_only=bool(pending.get("demo_read_only"))))
    except (ValueError, TypeError, KeyError) as exc:
        raise PermissionError("Сеанс подключения истёк") from exc
    await require_live_call_actor(session, actor, write=True)
    return actor
