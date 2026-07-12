import logging
from html import escape
from typing import Any

from aiogram import Bot
from aiohttp import ClientSession, ClientTimeout

from core.config import settings

logger = logging.getLogger(__name__)

class BotService:
    DISABLED_BOT_TOKEN_PLACEHOLDER = "0:disabled-bot-token"
    MAX_MESSAGE_LENGTH = 4096

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
    def escape_html(value: Any, *, max_length: int) -> str:
        """Escape an untrusted value while keeping the escaped output bounded."""
        raw_value = "" if value is None else str(value)
        rendered = escape(raw_value)
        if len(rendered) <= max_length:
            return rendered

        budget = max(0, max_length - 3)
        parts: list[str] = []
        used = 0
        for char in raw_value:
            escaped_char = escape(char)
            if used + len(escaped_char) > budget:
                break
            parts.append(escaped_char)
            used += len(escaped_char)
        return "".join(parts) + ("..." if max_length >= 3 else "")

    @staticmethod
    async def send_message(user_id: int, text: str, *, reply_markup: Any = None) -> bool:
        """
        Sends a message to a specific Telegram user.
        Uses the shared BOT_TOKEN from settings.
        """
        token = BotService._get_bot_token()
        if not token:
            logger.warning("Telegram message skipped because BOT_TOKEN is not configured")
            return False
        text_length = len(text) if isinstance(text, str) else 0
        if not text or not isinstance(text, str) or text_length > BotService.MAX_MESSAGE_LENGTH:
            logger.warning(
                "Telegram message skipped because text length is invalid user_id=%s length=%s",
                user_id,
                text_length,
            )
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
        except Exception as exc:
            logger.error(
                "Failed to send Telegram message user_id=%s error_type=%s",
                user_id,
                type(exc).__name__,
            )
            return False

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
            timeout = ClientTimeout(total=10.0)
            async with ClientSession(timeout=timeout) as client:
                body: dict[str, Any] = {
                    "chat_id": user_id,
                    "rich_message": {
                        "html": rich_html,
                    },
                }
                serialized_reply_markup = BotService._serialize_reply_markup(reply_markup)
                if serialized_reply_markup:
                    body["reply_markup"] = serialized_reply_markup

                async with client.post(
                    f"https://api.telegram.org/bot{token}/sendRichMessage",
                    json=body,
                ) as response:
                    payload = await response.json(content_type=None)
                    if response.status < 400 and payload.get("ok"):
                        return True
                    logger.warning(
                        "Telegram sendRichMessage returned non-ok response user_id=%s status_code=%s error_code=%s",
                        user_id,
                        response.status,
                        payload.get("error_code"),
                    )
        except Exception as exc:
            # HTTP client exception strings may contain the request URL,
            # including the bot token. Log only the exception type.
            logger.warning(
                "Failed to send Telegram rich message user_id=%s error_type=%s",
                user_id,
                type(exc).__name__,
            )

        if fallback_text:
            return await BotService.send_message(user_id, fallback_text, reply_markup=reply_markup)
        return False

    @staticmethod
    async def notify_installer_new_order(
        installer_tg_id: int,
        order_id: int,
        address: str,
        date_str: str,
        role: str,
    ) -> bool:
        """
        Specific template for notifying an installer about a new job.
        """
        text = (
            f"<b>👷‍♂️ Назначен новый монтаж!</b>\n\n"
            f"🆔 <b>Заказ №{order_id}</b>\n"
            f"📍 Адрес: {BotService.escape_html(address, max_length=500)}\n"
            f"📅 Дата: {BotService.escape_html(date_str, max_length=80)}\n"
            f"🔧 Роль: {BotService.escape_html(role, max_length=120)}\n\n"
            f"<i>Пожалуйста, подтвердите получение!</i>"
        )
        return await BotService.send_message(installer_tg_id, text)
