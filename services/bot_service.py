import logging
from typing import Any

import httpx
from aiogram import Bot

from core.config import settings

logger = logging.getLogger(__name__)

class BotService:
    DISABLED_BOT_TOKEN_PLACEHOLDER = "0:disabled-bot-token"

    @staticmethod
    def _get_bot_token() -> str | None:
        token = str(settings.BOT_TOKEN or "").strip()
        if not token or token == BotService.DISABLED_BOT_TOKEN_PLACEHOLDER:
            return None
        return token

    @staticmethod
    def _serialize_reply_markup(reply_markup: Any) -> dict[str, Any] | None:
        if reply_markup is None:
            return None
        if isinstance(reply_markup, dict):
            return reply_markup
        if hasattr(reply_markup, "model_dump"):
            return reply_markup.model_dump(exclude_none=True)
        return None

    @staticmethod
    async def send_message(user_id: int, text: str, *, reply_markup: Any = None):
        """
        Sends a message to a specific Telegram user.
        Uses the shared BOT_TOKEN from settings.
        """
        token = BotService._get_bot_token()
        if not token:
            logger.warning("Telegram message skipped because BOT_TOKEN is not configured")
            return
        try:
            bot = Bot(token=token)
            async with bot.context():
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {user_id}: {e}")

    @staticmethod
    async def send_rich_message(
        user_id: int,
        rich_html: str,
        *,
        fallback_text: str | None = None,
        reply_markup: Any = None,
    ) -> bool:
        """
        Send a Telegram Bot API 10.1 rich message.

        aiogram may lag behind new Bot API methods, so this uses the HTTP API
        directly and falls back to the existing HTML message path on failure.
        """
        token = BotService._get_bot_token()
        if not token:
            logger.warning("Telegram rich message skipped because BOT_TOKEN is not configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                body: dict[str, Any] = {
                    "chat_id": user_id,
                    "rich_message": {
                        "html": rich_html,
                    },
                }
                serialized_reply_markup = BotService._serialize_reply_markup(reply_markup)
                if serialized_reply_markup:
                    body["reply_markup"] = serialized_reply_markup

                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendRichMessage",
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("ok"):
                    return True
                logger.warning("Telegram sendRichMessage returned non-ok response: %s", payload)
        except Exception as exc:
            logger.warning("Failed to send Telegram rich message to %s: %s", user_id, exc)

        if fallback_text:
            await BotService.send_message(user_id, fallback_text, reply_markup=reply_markup)
        return False

    @staticmethod
    async def notify_installer_new_order(installer_tg_id: int, order_id: int, address: str, date_str: str, role: str):
        """
        Specific template for notifying an installer about a new job.
        """
        text = (
            f"<b>👷‍♂️ Назначен новый монтаж!</b>\n\n"
            f"🆔 <b>Заказ №{order_id}</b>\n"
            f"📍 Адрес: {address}\n"
            f"📅 Дата: {date_str}\n"
            f"🔧 Роль: {role}\n\n"
            f"<i>Пожалуйста, подтвердите получение!</i>"
        )
        await BotService.send_message(installer_tg_id, text)
