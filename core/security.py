"""JWT and cookie authentication helpers for protected API endpoints."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from services.staff_user_service import StaffUserService

# JWT CONFIG
# TODO: Move to settings in the future
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# OAuth2 scheme for Swagger UI (TokenUrl should point to login endpoint)
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/login/access-token",
    auto_error=False
)


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    auth_source: str
    staff_user_id: int | None = None
    role: str | None = None
    display_name: str | None = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def _extract_token(request: Request, token: Optional[str]) -> str:
    token_to_validate = token
    if not token_to_validate and request:
        token_to_validate = request.cookies.get("access_token")
        if token_to_validate and token_to_validate.startswith("Bearer "):
            token_to_validate = token_to_validate[7:]

    if not token_to_validate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_to_validate


async def get_current_auth_context(
    request: Request,
    token: Optional[str] = Depends(reusable_oauth2),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    """
    Unified Dependency for Authentication.
    Checks:
    1. Authorization Header (Bearer ...)
    2. Cookie (access_token)
    """
    token_to_validate = _extract_token(request, token)
        
    try:
        payload = jwt.decode(token_to_validate, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
             raise HTTPException(status_code=401, detail="Invalid token")

        auth_source = str(payload.get("auth_source") or "legacy")
        staff_user_id = payload.get("staff_user_id")
        if staff_user_id is not None:
            staff_user = await StaffUserService.get_by_id(session, int(staff_user_id))
            if staff_user is None or not StaffUserService.is_active(staff_user):
                raise HTTPException(status_code=401, detail="Invalid user")
            role = StaffUserService.primary_role(staff_user)
            if username != staff_user.username and username != str(staff_user.telegram_id or ""):
                raise HTTPException(status_code=401, detail="Invalid user")
            return AuthenticatedUser(
                username=username,
                staff_user_id=int(staff_user.id or 0),
                role=role,
                display_name=staff_user.display_name,
                auth_source=auth_source,
            )

        if username != settings.ADMIN_USERNAME:
             raise HTTPException(status_code=401, detail="Invalid user")

        return AuthenticatedUser(username=username, auth_source="legacy")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


async def get_current_user(
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> str:
    return auth.username


# Alias for backward compatibility if needed, but we should refactor usages.
get_current_username = get_current_user
