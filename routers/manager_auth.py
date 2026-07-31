from fastapi import APIRouter, Depends

from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import READ_USER_ME
from schemas import ManagerAuthStatusResponse


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
    }
