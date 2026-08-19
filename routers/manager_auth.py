from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_storefronts import ManagerStorefrontListResponse
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import LIST_MANAGER_STOREFRONTS, READ_USER_ME
from schemas import ManagerAuthStatusResponse
from services.manager_capability_service import ManagerCapabilityService
from services.manager_storefront_selector_service import ManagerStorefrontSelector


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/me", response_model=ManagerAuthStatusResponse, operation_id=READ_USER_ME)
async def check_auth_status(auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {
        "username": auth.username,
        "status": "authenticated",
        "staff_user_id": auth.staff_user_id,
        "role": auth.role,
        "display_name": auth.display_name,
        "auth_source": auth.auth_source,
        "tenant_id": auth.tenant_id,
        "storefront_id": auth.storefront_id,
        "tenant_membership_id": auth.tenant_membership_id,
        "is_system_tenant": auth.is_system_tenant,
        "capabilities": ManagerCapabilityService.for_auth(auth),
    }


@router.get(
    "/storefronts",
    response_model=ManagerStorefrontListResponse,
    operation_id=LIST_MANAGER_STOREFRONTS,
)
async def list_manager_storefronts(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await ManagerStorefrontSelector.list_available(
        session,
        tenant_scope=auth.tenant_scope(),
    )
