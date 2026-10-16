"""Trusted polling transport for Telegram proof; intentionally permits unlinked senders."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import BotAccountLinkClaimRequest, BotAccountLinkClaimResponse, BotTelegramLoginDecisionRequest, BotTelegramLoginDecisionResponse
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.staff_telegram_service import StaffTelegramService
from services.staff_telegram_security import telegram_errors

router = APIRouter(prefix="/api/internal/bot/v1/account-links", tags=["internal bot v1"], dependencies=[Depends(require_bot_api_token)])


@router.post("/claim", response_model=BotAccountLinkClaimResponse, operation_id="claim_internal_bot_account_link_v1")
async def claim_account_link(payload: BotAccountLinkClaimRequest, session: AsyncSession = Depends(get_session)):
    """Claim a short-lived link/login token using the sender of a real private /start update. Requires service BOT_API_TOKEN, not Manager credentials. Link claims need not be existing staff and only stage proof; final browser confirmation owns the write. Login claims require an already linked active identity. Same-sender delivery retry is safe; another sender409, unknown/expired token404/409. Never merges accounts or issues a user JWT."""
    async with telegram_errors(session):
        return await StaffTelegramService.claim(session, **payload.model_dump())


@router.post("/login-decision", response_model=BotTelegramLoginDecisionResponse, operation_id="decide_internal_bot_telegram_login_v1")
async def decide_login(payload: BotTelegramLoginDecisionRequest, session: AsyncSession = Depends(get_session)):
    """Record the actual private Telegram sender's approve/deny callback after displaying the matching browser code. Requires BOT_API_TOKEN; only the original claimant may decide. Approval revalidates the current linked account and auth_version. Only the originating browser can consume this approval via POST /login/telegram/challenges/{id}/complete."""
    async with telegram_errors(session):
        return await StaffTelegramService.decide(session, **payload.model_dump())
