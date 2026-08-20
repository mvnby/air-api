"""One cookie contract shared by manager login, logout, and credential rotation."""

from datetime import timedelta

from fastapi import Response

from core.config import settings


AUTH_COOKIE_NAME = "access_token"


def set_auth_cookie(response: Response, access_token: str, expires_delta: timedelta) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=int(expires_delta.total_seconds()),
        expires=int(expires_delta.total_seconds()),
        samesite="lax",
        secure=settings.is_production,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
