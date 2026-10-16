"""Bot-mediated login without Telegram Widget domains or new OAuth secrets."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_telegram import TelegramChallengeResponse, TelegramChallengeStartResponse
from core.database import get_session
from services.login_throttle_service import LoginThrottleExceeded
from services.telegram_login_throttle_service import TelegramLoginThrottleService
from services.client_address_service import ClientAddressService
from services.staff_telegram_service import StaffTelegramService
from services.staff_telegram_security import cookie_name, issue_staff_cookie, require_same_origin, set_browser_cookie, telegram_errors

router = APIRouter(prefix="/login/telegram/challenges", tags=["login"])


@router.post("", response_model=TelegramChallengeStartResponse, operation_id="start_telegram_login")
async def start_login(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    """Create a rate-limited five-minute anonymous browser login challenge. Requires X-Kitlane-Telegram:1 and approved Origin. Returns a deep link and eight-digit browser matching code; the private bot must explicitly approve. This operation creates no staff account and issues no login cookie."""
    async with telegram_errors(session):
        require_same_origin(request)
        source = ClientAddressService.normalize(request.client.host if request.client else None)
        try:
            decision = await TelegramLoginThrottleService.record_failure(session, f"telegram-challenge:{source}", source)
        except LoginThrottleExceeded as exc:
            raise HTTPException(status_code=429, detail={"code": "login_rate_limited"}, headers={"Retry-After": str(exc.retry_after_seconds)}) from None
        if decision.blocked:
            raise HTTPException(status_code=429, detail={"code": "login_rate_limited"}, headers={"Retry-After": str(decision.retry_after_seconds)})
        result, secret = await StaffTelegramService.start(session, purpose="login", browser_secret=request.cookies.get(cookie_name("login")))
        set_browser_cookie(response, "login", secret)
        return result


@router.get("/{challenge_id}", response_model=TelegramChallengeResponse, operation_id="get_telegram_login")
async def login_status(challenge_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    """Read pending/approved/denied/expired status only with the originating browser secret. Does not log in or consume the approval; mismatched browser returns404."""
    async with telegram_errors(session):
        return await StaffTelegramService.status(session, challenge_id=challenge_id, browser_secret=request.cookies.get(cookie_name("login")), purpose="login")


@router.post("/{challenge_id}/complete", operation_id="complete_telegram_login")
async def complete_login(challenge_id: str, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    """Consume an explicit bot approval in its original browser. Requires X-Kitlane-Telegram:1 and approved Origin; revalidates active identity, unchanged auth_version, live membership and legacy-owner fence. Issues the normal HttpOnly login cookie and JWT response. Replay/expiry or changed access rejects the login; never creates an account."""
    async with telegram_errors(session):
        require_same_origin(request)
        user = await StaffTelegramService.complete_login(session, challenge_id=challenge_id, browser_secret=request.cookies.get(cookie_name("login")))
        return issue_staff_cookie(response, user)
