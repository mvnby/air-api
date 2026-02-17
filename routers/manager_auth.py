from fastapi import APIRouter, Depends

from core.security import get_current_username
from routers.manager_operation_ids import READ_USER_ME


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/me", operation_id=READ_USER_ME)
async def check_auth_status(username: str = Depends(get_current_username)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {"username": username, "status": "authenticated"}
