"""
HTTP Basic Authentication for SQLAdmin and FastAPI endpoints.
"""
import secrets
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from core.config import settings


class AdminAuthBackend(AuthenticationBackend):
    """
    Authentication backend for SQLAdmin using HTTP Basic Auth credentials.
    Implements session-based authentication for the admin panel.
    """
    
    async def login(self, request: Request) -> bool:
        """
        Handle login form submission.
        Validates username and password from the form data.
        """
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        # Validate credentials using timing-safe comparison
        username_correct = secrets.compare_digest(
            str(username).encode("utf8"),
            settings.ADMIN_USERNAME.encode("utf8")
        )
        password_correct = secrets.compare_digest(
            str(password).encode("utf8"),
            settings.ADMIN_PASSWORD.encode("utf8")
        )
        
        if username_correct and password_correct:
            # Store authentication in session
            request.session.update({"authenticated": True})
            return True
        
        return False
    
    async def logout(self, request: Request) -> bool:
        """
        Handle logout request.
        Clears the authentication session.
        """
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        """
        Check if the user is authenticated.
        Called on every request to protected admin routes.
        """
        return request.session.get("authenticated", False)


# HTTP Basic Auth for FastAPI endpoints
security = HTTPBasic()


def get_current_username(
    credentials: HTTPBasicCredentials = Depends(security)
) -> str:
    """
    FastAPI dependency for HTTP Basic Authentication.
    
    Usage:
        @app.get("/protected")
        async def protected_route(username: str = Depends(get_current_username)):
            return {"message": f"Hello, {username}!"}
    
    Args:
        credentials: HTTP Basic Auth credentials from request header
        
    Returns:
        Username if authentication successful
        
    Raises:
        HTTPException: 401 Unauthorized if credentials are invalid
    """
    # Use secrets.compare_digest to prevent timing attacks
    username_correct = secrets.compare_digest(
        credentials.username.encode("utf8"),
        settings.ADMIN_USERNAME.encode("utf8")
    )
    password_correct = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.ADMIN_PASSWORD.encode("utf8")
    )
    
    if not (username_correct and password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username


async def check_admin_session(request: Request) -> bool:
    """
    FastAPI dependency for session-based authentication (SQLAdmin).
    Use this for endpoints that are called from the admin panel via AJAX.
    
    Usage:
        @router.get("/admin/stats")
        async def get_stats(authenticated: bool = Depends(check_admin_session)):
            return {"data": "..."}
    
    Args:
        request: FastAPI Request object
        
    Returns:
        True if authenticated
        
    Raises:
        HTTPException: 401 Unauthorized if not authenticated
    """
    if not request.session.get("authenticated", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login to admin panel first.",
        )
    return True
