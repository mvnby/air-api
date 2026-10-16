"""Self-service identity proof, separate from company staff administration."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_telegram import (
    TelegramChallengeResponse, TelegramChallengeStartResponse, TelegramDisconnectPayload,
    TelegramLinkConfirmPayload, TelegramLinkedResponse,
)
from core.database import get_session
from core.security import AuthenticatedUser, require_personal_workspace_access
from services.staff_telegram_service import StaffTelegramService
from services.staff_telegram_security import cookie_name, issue_staff_cookie, require_same_origin, set_browser_cookie, telegram_errors

router = APIRouter(prefix="/api/manager/account/telegram", tags=["manager-account-telegram"])


@router.post("/link-challenges", response_model=TelegramChallengeStartResponse, operation_id="start_manager_telegram_link")
async def start_link(request: Request, response: Response, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access)):
    """Create a five-minute proof for this account and browser. Requires X-Kitlane-Telegram:1 and approved Origin. Returns a private-bot deep link, never a Telegram numeric-ID input. A new challenge replaces pending challenges; no account is linked yet."""
    async with telegram_errors(session):
        require_same_origin(request)
        result, secret = await StaffTelegramService.start(session, purpose="link", browser_secret=request.cookies.get(cookie_name("link")), auth=auth)
        set_browser_cookie(response, "link", secret)
        return result


@router.get("/link-challenges/{challenge_id}", response_model=TelegramChallengeResponse, operation_id="get_manager_telegram_link")
async def link_status(challenge_id: str, request: Request, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access)):
    """Read the candidate Telegram profile only in the originating browser and unchanged account session. Unknown/browser-mismatched challenges return404; expired proofs report expired. This GET never links or consumes a proof."""
    async with telegram_errors(session):
        return await StaffTelegramService.status(session, challenge_id=challenge_id, browser_secret=request.cookies.get(cookie_name("link")), purpose="link", auth=auth)


@router.post("/link-challenges/{challenge_id}/confirm", response_model=TelegramLinkedResponse, operation_id="confirm_manager_telegram_link")
async def confirm_link(challenge_id: str, payload: TelegramLinkConfirmPayload, request: Request, response: Response, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access)):
    """Confirm exactly the bot-proven profile shown by the browser. Atomically links the current account, records proof/audit and rotates auth_version, refreshing this browser cookie. Requires the original challenge cookie, X-Kitlane-Telegram:1 and approved Origin. Expired/replayed/conflicting proofs return409; an existing other account is never merged or stolen."""
    async with telegram_errors(session):
        require_same_origin(request)
        user = await StaffTelegramService.confirm(session, challenge_id=challenge_id, browser_secret=request.cookies.get(cookie_name("link")), auth=auth, telegram_id=payload.telegram_id)
        issue_staff_cookie(response, user, auth_source=auth.auth_source)
        return {"status": "linked", "telegram_id": user.telegram_id, "telegram_username": user.telegram_username,
                "telegram_notifications_enabled": user.telegram_notifications_enabled}


@router.delete("", status_code=204, operation_id="disconnect_manager_telegram")
async def disconnect(payload: TelegramDisconnectPayload, request: Request, response: Response, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access)):
    """Remove this account's Telegram binding only after verifying its alternate username/password login. Clears the contractor mirror, rotates auth_version and refreshes the current browser cookie. Requires X-Kitlane-Telegram:1 and approved Origin; no alternate factor returns409. Does not delete the account or revoke company membership."""
    async with telegram_errors(session):
        require_same_origin(request)
        user = await StaffTelegramService.disconnect(session, auth=auth, current_password=payload.current_password)
        issue_staff_cookie(response, user, auth_source="staff_password")
