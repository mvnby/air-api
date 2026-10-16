"""Task delivery follows a live explicit grant in the event company, never bot selection."""

from core.security import AuthenticatedUser
from models.tenancy import TenantScope, Storefront
from services.installer_work_urls import installer_work_url
from services.worker_assignment_access_service import WorkerAssignmentAccessService
from services.worker_assignment_service import WorkerAssignmentError


async def task_notification_assignment(session, staff_user, *, scope, stage_id, for_update=False):
    auth = AuthenticatedUser(username=staff_user.username or str(staff_user.telegram_id or staff_user.id),
        auth_source="notification", staff_user_id=staff_user.id, auth_version=staff_user.auth_version,
        tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, is_system_tenant=scope.is_system)
    try:
        return await WorkerAssignmentAccessService.get_for_stage(session, auth, stage_id, for_update=for_update)
    except WorkerAssignmentError:
        return None


async def task_notification_allowed(session, staff_user, payload, *, for_update=False) -> bool:
    # Old queued payloads have no reviewed assignment binding and may contain
    # internal stage titles/CRM links. Never send them after this boundary changes.
    if payload.assignment_id is None or payload.tenant_id is None or payload.storefront_id is None:
        return False
    scope = TenantScope(tenant_id=payload.tenant_id, storefront_id=payload.storefront_id)
    assignment = await task_notification_assignment(session, staff_user, scope=scope, stage_id=payload.stage_id, for_update=for_update)
    if assignment is None or assignment.id != payload.assignment_id or assignment.order_id != payload.order_id:
        return False
    site = await session.get(Storefront, scope.storefront_id, populate_existing=True)
    return bool(site and site.tenant_id == scope.tenant_id and site.status == "active"
        and payload.stage_name == assignment.title
        and payload.manager_url == installer_work_url(assignment.id, tenant_id=scope.tenant_id, storefront_slug=site.slug))
