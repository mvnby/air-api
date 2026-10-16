"""Browser proof, safe public bot URL, and cookies for Telegram challenges."""

import hashlib
import os
import re
import secrets
from urllib.parse import urlsplit
from contextlib import asynccontextmanager

from fastapi import Request, Response

from core.config import settings


class StaffTelegramError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_name(purpose: str) -> str:
    return f"kitlane_tg_{purpose}"


def set_browser_cookie(response: Response, purpose: str, secret: str) -> None:
    response.set_cookie(cookie_name(purpose), secret, httponly=True, secure=settings.is_production,
                        samesite="lax", max_age=300, path="/")


def require_browser(row, browser_secret: str | None) -> None:
    if not browser_secret or not secrets.compare_digest(row.browser_hash, digest(browser_secret)):
        raise StaffTelegramError("telegram_challenge_not_found", "Подключение не найдено в этом браузере", 404)


def require_same_origin(request: Request) -> None:
    """Sensitive JSON writes require an approved browser origin and custom header.

    A hostile form cannot set this header, and cross-origin JS needs a CORS
    preflight. Validate Origin independently of ambient authentication cookies.
    """
    if request.headers.get("X-Kitlane-Telegram") != "1":
        raise StaffTelegramError("telegram_csrf", "Обновите страницу и повторите действие", 403)
    origin = request.headers.get("origin")
    if origin:
        allowed = {str(value).rstrip("/") for value in settings.CORS_ORIGINS}
        allowed.add(f"{request.url.scheme}://{request.url.netloc}")
        if origin.rstrip("/") not in allowed:
            raise StaffTelegramError("telegram_csrf", "Источник запроса не разрешён", 403)
    elif request.headers.get("sec-fetch-site") == "cross-site":
        raise StaffTelegramError("telegram_csrf", "Источник запроса не разрешён", 403)


async def bot_username() -> str:
    # Existing deployment setting is public metadata, not a new OAuth secret.
    username = str(os.environ.get("TELEGRAM_BOT_USERNAME") or os.environ.get("VITE_TELEGRAM_LOGIN_BOT_USERNAME") or "").strip().lstrip("@")
    if not username:
        token = str(settings.BOT_TOKEN or "").strip()
        if not token or token == "0:disabled-bot-token":
            raise StaffTelegramError("telegram_unavailable", "Telegram временно недоступен", 503)
        from aiogram import Bot
        try:
            async with Bot(token=token).context() as bot:
                username = (await bot.get_me()).username or ""
        except Exception:
            raise StaffTelegramError("telegram_unavailable", "Telegram временно недоступен", 503) from None
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise StaffTelegramError("telegram_unavailable", "Telegram временно недоступен", 503)
    return username


@asynccontextmanager
async def telegram_errors(session):
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityError
    from services.manager_tenant_access_service import ManagerTenantAccessResolutionError
    try:
        yield
    except StaffTelegramError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except LegacyOwnerManagedIdentityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except ManagerTenantAccessResolutionError as exc:
        await session.rollback()
        raise HTTPException(status_code=403, detail={"code": "telegram_login_unavailable", "message": "Активный доступ к компании не найден"}) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "telegram_already_linked", "message": "Этот Telegram уже связан с другой учётной записью"}) from exc


def issue_staff_cookie(response, user, *, auth_source="telegram"):
    from datetime import timedelta
    from core.auth_cookie import set_auth_cookie
    from core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
    token = create_access_token({
        "sub": user.username or str(user.telegram_id), "staff_user_id": user.id,
        "auth_version": user.auth_version, "auth_source": auth_source,
    }, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    set_auth_cookie(response, token, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}
