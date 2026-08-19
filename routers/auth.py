from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from core.config import settings
from core.database import get_session
from schemas import TelegramLoginPayload
from services.staff_user_service import StaffUserService
import secrets

router = APIRouter(tags=["login"])


def _set_auth_cookie(response: Response, access_token: str, expires_delta: timedelta) -> None:
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=int(expires_delta.total_seconds()),
        expires=int(expires_delta.total_seconds()),
        samesite="lax",
        secure=settings.is_production,
    )


def _token_response(response: Response, token_data: dict[str, Any]) -> dict[str, str]:
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)
    _set_auth_cookie(response, access_token, access_token_expires)
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/login/access-token", operation_id="login_access_token")
async def login_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    Sets 'access_token' cookie as well.
    """
    staff_user = await StaffUserService.authenticate_password(session, form_data.username, form_data.password)
    if staff_user is not None:
        username = staff_user.username or str(staff_user.telegram_id or staff_user.id)
        return _token_response(
            response,
            {
                "sub": username,
                "staff_user_id": staff_user.id,
                "role": StaffUserService.primary_role(staff_user),
                "auth_source": "staff_password",
            },
        )

    # Legacy emergency access from env.
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

    return _token_response(response, {"sub": form_data.username, "auth_source": "legacy"})


@router.post(
    "/login/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="logout_access_token",
)
async def logout(response: Response) -> None:
    """End the browser cookie session without requiring a valid token.

    Access tokens are intentionally stateless JWTs, so this endpoint cannot
    revoke a token that was deliberately copied to an Authorization header.
    The manager UI uses the HttpOnly cookie only; deleting the cookie is the
    server-side session boundary for a normal browser logout.
    """
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )


@router.post("/login/telegram", operation_id="login_telegram")
async def login_telegram(
    payload: TelegramLoginPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Any:
    staff_user = await StaffUserService.authenticate_telegram_login(
        session,
        payload.model_dump(exclude_none=True),
    )
    if staff_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram login is not allowed")

    username = staff_user.username or str(staff_user.telegram_id or staff_user.id)
    return _token_response(
        response,
        {
            "sub": username,
            "staff_user_id": staff_user.id,
            "role": StaffUserService.primary_role(staff_user),
            "auth_source": "telegram",
        },
    )
