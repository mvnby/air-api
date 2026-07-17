"""Telegram-only delivery helpers kept outside the backend service layer."""

import logging
from typing import Any

from aiogram import Bot
from aiohttp import ClientSession, ClientTimeout

from .settings import settings


logger = logging.getLogger(__name__)


class BotTelegramService:
    MAX_MESSAGE_LENGTH = 4096

    @staticmethod
    def _token() -> str | None:
        token = str(settings.BOT_TOKEN or "").strip()
        return token if token and token != "0:disabled-bot-token" else None

    @staticmethod
    def _reply_markup(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        return value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else None

    @classmethod
    async def send_message(cls, user_id: int, text: str, *, reply_markup: Any = None) -> bool:
        token = cls._token()
        if not token or not text or len(text) > cls.MAX_MESSAGE_LENGTH:
            return False
        try:
            bot = Bot(token=token)
            async with bot.context():
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            return True
        except Exception:
            logger.warning("Telegram fallback message failed user_id=%s", user_id, exc_info=True)
            return False

    @classmethod
    async def send_rich_message(
        cls,
        user_id: int,
        rich_html: str,
        *,
        fallback_text: str | None = None,
        reply_markup: Any = None,
    ) -> bool:
        token = cls._token()
        if not token:
            return False
        try:
            async with ClientSession(timeout=ClientTimeout(total=10.0)) as client:
                body: dict[str, Any] = {
                    "chat_id": user_id,
                    "rich_message": {"html": rich_html},
                }
                serialized = cls._reply_markup(reply_markup)
                if serialized:
                    body["reply_markup"] = serialized
                async with client.post(
                    f"https://api.telegram.org/bot{token}/sendRichMessage", json=body
                ) as response:
                    payload = await response.json(content_type=None)
                    if response.status < 400 and payload.get("ok"):
                        return True
        except Exception:
            logger.warning("Telegram rich message failed user_id=%s", user_id, exc_info=True)
        if fallback_text:
            return await cls.send_message(user_id, fallback_text, reply_markup=reply_markup)
        return False
