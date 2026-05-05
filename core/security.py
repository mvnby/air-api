"""JWT and cookie authentication helpers for protected API endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt

from core.config import settings

# JWT CONFIG
# TODO: Move to settings in the future
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# OAuth2 scheme for Swagger UI (TokenUrl should point to login endpoint)
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/login/access-token",
    auto_error=False
)

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

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(reusable_oauth2)
) -> str:
    """
    Unified Dependency for Authentication.
    Checks:
    1. Authorization Header (Bearer ...)
    2. Cookie (access_token)
    """
    
    # 1. Try Token from Header (OAuth2PasswordBearer)
    token_to_validate = token

    # 2. If no header, try Cookie
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
        
    try:
        payload = jwt.decode(token_to_validate, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
             raise HTTPException(status_code=401, detail="Invalid token")
             
        # Optional: Verify username against settings
        if username != settings.ADMIN_USERNAME:
             raise HTTPException(status_code=401, detail="Invalid user")
             
        return username
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


# Alias for backward compatibility if needed, but we should refactor usages.
get_current_username = get_current_user
