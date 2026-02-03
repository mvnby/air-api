"""
HTTP Basic Authentication for SQLAdmin and FastAPI endpoints.
Now updated to support JWT and Cookie Authentication.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordBearer
from sqladmin.authentication import AuthenticationBackend
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

class AdminAuthBackend(AuthenticationBackend):
    """
    Authentication backend for SQLAdmin using HTTP Basic Auth credentials OR JWT Cookie.
    """
    
    async def login(self, request: Request) -> bool:
        """
        Handle login form submission (legacy/basic auth logic).
        For SQLAdmin, we still support session-based or just check cookie.
        """
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        # Validate credentials
        username_correct = secrets.compare_digest(
            str(username).encode("utf8"),
            settings.ADMIN_USERNAME.encode("utf8")
        )
        password_correct = secrets.compare_digest(
            str(password).encode("utf8"),
            settings.ADMIN_PASSWORD.encode("utf8")
        )
        
        if username_correct and password_correct:
            request.session.update({"authenticated": True})
            return True
        
        return False
    
    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        """
        Check authentication via Session OR JWT Cookie.
        """
        # 1. Check Session (Legacy/Direct SQLAdmin Login)
        if request.session.get("authenticated", False):
            return True
            
        # 2. Check JWT Cookie (Unified Auth)
        token = request.cookies.get("access_token")
        if token:
            # Clean "Bearer " prefix if present
            if token.startswith("Bearer "):
                token = token[7:]
            
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username == settings.ADMIN_USERNAME:
                    return True
            except jwt.PyJWTError:
                pass
                
        return False

# HTTP Basic Auth instance (Legacy)
security = HTTPBasic()

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
        # Fallback to HTTP Basic? Or just raise 401?
        # For API, we prefer 401. 
        # But wait, original code used HTTPBasic for simple auth.
        # Let's support both if needed, but for now we enforce Bearer/Cookie.
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

async def check_admin_session(request: Request) -> bool:
    """
    Dependency for SQLAdmin-related AJAX checks.
    Uses the new AdminAuthBackend logic effectively.
    """
    backend = AdminAuthBackend(secret_key=settings.SECRET_KEY)
    is_auth = await backend.authenticate(request)
    if not is_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return True
