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
    LoginAttemptReservation,
    LoginThrottleExceeded,
    LoginThrottleService,
)
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.credential_service import CredentialService
from services.staff_user_service import StaffUserService
from services.legacy_owner_managed_identity_service import (
    LegacyOwnerManagedIdentityService,
)

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


async def _reject_password_login(
    session: AsyncSession,
    *,
    username: str,
    source: str,
    reservation: LoginAttemptReservation,
) -> None:
    throttle = await LoginThrottleService.record_failure(
        session,
        username,
        source,
        reservation=reservation,
    )
    if throttle.blocked:
        raise _login_rate_limited(throttle.retry_after_seconds)
    raise HTTPException(status_code=400, detail="Incorrect username or password")


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

    legacy_username = LegacyOwnerAuthGuard.configured_username_matches(
        form_data.username
    )
    legacy_state = (
        await LegacyOwnerAuthGuard.state(session, for_update=True)
        if legacy_username
        else None
    )

    if legacy_state is not None and legacy_state.mode == LegacyOwnerAuthGuard.MODE_LEGACY:
        # Keep bcrypt work cost-matched while the explicit legacy mode gives
        # the env credential priority over any colliding StaffUser record.
        await CredentialService.verify_password_async(
            form_data.password,
            CredentialService.DUMMY_PASSWORD_HASH,
        )
        password_correct = _constant_time_text_equal(
            form_data.password,
            settings.ADMIN_PASSWORD,
        )
        if not password_correct:
            await _reject_password_login(
                session,
                username=form_data.username,
                source=source,
                reservation=reservation,
            )
        await LoginThrottleService.clear(session, form_data.username)
        return _token_response(
            response,
            {
                "sub": form_data.username,
                "auth_source": "legacy",
                "legacy_auth_version": int(legacy_state.legacy_token_version),
            },
        )

    authentication = await StaffUserService.authenticate_password(
        session, form_data.username, form_data.password
    )
    if authentication is not None:
        current_legacy_state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_staff_identity(
            current_legacy_state,
            staff_user_id=int(authentication.user.id or 0),
            username=str(authentication.user.username or ""),
        ):
            await _reject_password_login(
                session,
                username=form_data.username,
                source=source,
                reservation=reservation,
            )
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

    await _reject_password_login(
        session,
        username=form_data.username,
        source=source,
        reservation=reservation,
    )


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
    telegram_payload = payload.model_dump(exclude_none=True)
    if (
        not StaffUserService.verify_telegram_login_payload(telegram_payload)
        or not await LegacyOwnerManagedIdentityService.telegram_login_allowed(
            session,
            telegram_id=payload.id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram login is not allowed",
        )
    staff_user = await StaffUserService.authenticate_telegram_login(
        session,
        telegram_payload,
    )
    if staff_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram login is not allowed")

    legacy_owner_state = await LegacyOwnerAuthGuard.state(session)
    if not LegacyOwnerAuthGuard.allows_staff_identity(
        legacy_owner_state,
        staff_user_id=int(staff_user.id or 0),
        username=str(staff_user.username or ""),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram login is not allowed",
        )

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
