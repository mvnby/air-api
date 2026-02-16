from fastapi import APIRouter, Depends

from core.security import get_current_username


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/me", operation_id="read_user_me")
async def check_auth_status(username: str = Depends(get_current_username)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {"username": username, "status": "authenticated"}
