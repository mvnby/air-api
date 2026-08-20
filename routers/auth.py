import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from core.auth_cookie import clear_auth_cookie, set_auth_cookie
from core.config import settings
from core.database import get_session
from schemas import TelegramLoginPayload
from services.client_address_service import ClientAddressService
from services.login_throttle_service import (
    LoginThrottleExceeded,
    LoginThrottleService,
)
from services.staff_user_service import StaffUserService

router = APIRouter(tags=["login"])


def _constant_time_text_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(
        left.encode("utf-8", errors="surrogatepass"),
        right.encode("utf-8", errors="surrogatepass"),
    )


def _login_rate_limited(retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "login_rate_limited",
            "message": "Too many login attempts. Try again later.",
        },
        headers={"Retry-After": str(max(1, int(retry_after_seconds)))},
    )


def _token_response(response: Response, token_data: dict[str, Any]) -> dict[str, str]:
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)
    set_auth_cookie(response, access_token, access_token_expires)
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/login/access-token", operation_id="login_access_token")
async def login_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    Sets 'access_token' cookie as well.
    """
    source = ClientAddressService.normalize(
        request.client.host if request.client is not None else None
    )
    try:
        reservation = await LoginThrottleService.reserve_attempt(
            session,
            form_data.username,
            source,
        )
    except LoginThrottleExceeded as exc:
        raise _login_rate_limited(exc.retry_after_seconds) from None

    authentication = await StaffUserService.authenticate_password(
        session,
        form_data.username,
        form_data.password,
    )
    if authentication is not None:
        await LoginThrottleService.clear(session, form_data.username)
        staff_user = authentication.user
        username = staff_user.username or str(staff_user.telegram_id or staff_user.id)
        return _token_response(
            response,
            {
                "sub": username,
                "staff_user_id": staff_user.id,
                "role": StaffUserService.primary_role(staff_user),
                "auth_source": "staff_password",
                "auth_version": authentication.auth_version,
            },
        )

    # Legacy emergency access from env.
    username_correct = _constant_time_text_equal(
        form_data.username,
        settings.ADMIN_USERNAME,
    )
    password_correct = _constant_time_text_equal(
        form_data.password,
        settings.ADMIN_PASSWORD,
    )

    if not (username_correct and password_correct):
        throttle = await LoginThrottleService.record_failure(
            session,
            form_data.username,
            source,
            reservation=reservation,
        )
        if throttle.blocked:
            raise _login_rate_limited(throttle.retry_after_seconds)
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    await LoginThrottleService.clear(session, form_data.username)
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
    clear_auth_cookie(response)


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
            "auth_version": staff_user.auth_version,
        },
    )
