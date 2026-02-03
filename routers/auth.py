from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from core.config import settings
import secrets

router = APIRouter(tags=["login"])

@router.post("/login/access-token", operation_id="login_access_token")
def login_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    Sets 'access_token' cookie as well.
    """
    # 1. Validate Credentials
    username_correct = secrets.compare_digest(
        form_data.username.encode("utf8"),
        settings.ADMIN_USERNAME.encode("utf8")
    )
    password_correct = secrets.compare_digest(
        form_data.password.encode("utf8"),
        settings.ADMIN_PASSWORD.encode("utf8")
    )
    
    if not (username_correct and password_correct):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # 2. Create Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    
    # 3. Set Cookie
    # We set "Bearer <token>" or just "<token>"?
    # User request: value=f"Bearer {access_token}"
    cookie_value = f"Bearer {access_token}"
    
    response.set_cookie(
        key="access_token",
        value=cookie_value,
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
        expires=int(access_token_expires.total_seconds()),
        samesite="lax",
        secure=settings.is_production, # Set to True in Prod with HTTPS
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
