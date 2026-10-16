"""Browser and existing bot-service transport for Telegram identity proof."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TelegramProfile(BaseModel):
    id: int = Field(gt=0)
    username: str | None = None
    display_name: str


class TelegramChallengeResponse(BaseModel):
    challenge_id: str
    expires_at: datetime
    status: Literal["pending", "claimed", "confirmed", "expired", "canceled", "approval_pending", "approved", "denied", "completed"]
    telegram: TelegramProfile | None = None


class TelegramChallengeStartResponse(TelegramChallengeResponse):
    deep_link: str
    browser_code: str | None = None


class TelegramLinkConfirmPayload(BaseModel):
    telegram_id: int = Field(gt=0)


class TelegramLinkedResponse(BaseModel):
    status: Literal["linked"] = "linked"
    telegram_id: int
    telegram_username: str | None
    telegram_notifications_enabled: bool


class TelegramDisconnectPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
