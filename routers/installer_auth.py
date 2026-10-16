"""Read-only installer bootstrap; never exposes Manager CRM capabilities."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_storefronts import ManagerStorefrontListResponse
from core.database import get_session
from core.security import AuthenticatedUser, get_current_installer_context
from routers.installer_operation_ids import LIST_INSTALLER_STOREFRONTS, READ_INSTALLER_ME
from schemas import ManagerAuthStatusResponse
from services.manager_storefront_selector_service import ManagerStorefrontSelector
from services.staff_avatar_service import staff_avatar_url
from services.staff_user_service import StaffUserService

router = APIRouter(prefix="/api/installer", tags=["installer-auth"])


@router.get("/me", response_model=ManagerAuthStatusResponse, operation_id=READ_INSTALLER_ME)
async def read_installer_me(
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Read live identity and the selected real company/site for My Work.

    Accepts the existing Manager company/storefront headers. An invalid explicit
    selection is denied, never replaced. Only actual owner/admin/manager/installer
    membership is eligible; virtual platform support and catalog editors are denied.
    This bootstrap grants no assignment, CRM or write access.
    """
    user = await StaffUserService.get_by_id(session, auth.staff_user_id)
    return {
        "username": auth.username, "status": "authenticated", "staff_user_id": auth.staff_user_id,
        "role": auth.role, "display_name": auth.display_name,
        "avatar_url": staff_avatar_url(user, tenant_id=auth.tenant_id) if user else None,
        "auth_source": auth.auth_source, "tenant_id": auth.tenant_id, "storefront_id": auth.storefront_id,
        "tenant_membership_id": auth.tenant_membership_id, "is_system_tenant": auth.is_system_tenant,
        "capabilities": ["installer.works.read"], "can_change_password": auth.can_change_password,
        "must_change_password": auth.must_change_password, "demo_read_only": auth.demo_read_only,
        "is_platform_owner": auth.is_platform_owner, "access_kind": "membership",
    }


@router.get("/storefronts", response_model=ManagerStorefrontListResponse, operation_id=LIST_INSTALLER_STOREFRONTS)
async def list_installer_storefronts(
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """List active sites of the selected real company, without switching context.

    Uses the same fresh membership and explicit selection checks as /installer/me.
    Listing a site grants no assignment or Manager access.
    """
    return await ManagerStorefrontSelector.list_available(session, tenant_scope=auth.tenant_scope())
