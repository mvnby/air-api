from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramConflictError,
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, ReplyParameters

from core.config import settings
from services.communications.providers.base import ProviderDeliveryResult, TelegramMessageOptions


logger = logging.getLogger(__name__)


class TelegramDeliveryProvider:
    """A reusable Telegram adapter with stable, secret-safe error outcomes."""

    channel = "telegram"
    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, *, token: str, request_timeout_seconds: float = 15.0) -> None:
        normalized_token = str(token or "").strip()
        if not normalized_token or normalized_token == "0:disabled-bot-token":
            raise ValueError("Telegram provider token is required")
        normalized_timeout = float(request_timeout_seconds)
        if not 1.0 <= normalized_timeout <= 60.0:
            raise ValueError("Telegram provider timeout must be between 1 and 60 seconds")
        self._bot = Bot(token=normalized_token)
        self._request_timeout_seconds = normalized_timeout

    async def close(self) -> None:
        await self._bot.session.close()

    async def send(
        self,
        *,
        destination: str,
        text: str,
        delivery_id: str,
        options: TelegramMessageOptions | None = None,
    ) -> ProviderDeliveryResult:
        normalized_delivery_id = str(delivery_id or "").strip()
        if not normalized_delivery_id:
            raise ValueError("Communication delivery ID is required")
        normalized_text = text if isinstance(text, str) else ""
        if not normalized_text or len(normalized_text) > self.MAX_MESSAGE_LENGTH:
            return ProviderDeliveryResult.permanent_failure(
                category="payload",
                code="telegram_text_invalid",
                message="Rendered Telegram text is empty or exceeds the provider limit",
            )
        try:
            normalized_destination = int(str(destination).strip())
        except (TypeError, ValueError):
            return ProviderDeliveryResult.permanent_failure(
                category="recipient",
                code="telegram_destination_invalid",
                message="Telegram destination is invalid",
            )
        if normalized_destination == 0:
            return ProviderDeliveryResult.permanent_failure(
                category="recipient",
                code="telegram_destination_invalid",
                message="Telegram destination is invalid",
            )

        try:
            async with asyncio.timeout(self._request_timeout_seconds):
                message_id = await self._deliver(normalized_destination, normalized_text, options)
            return ProviderDeliveryResult.sent(message_id)
        except TelegramRetryAfter as exc:
            return ProviderDeliveryResult.transient_failure(
                category="rate_limit",
                code="telegram_retry_after",
                message="Telegram rate limit requires a delayed retry",
                retry_after_seconds=max(1, int(exc.retry_after)),
            )
        except TelegramEntityTooLarge:
            return ProviderDeliveryResult.permanent_failure(
                category="payload",
                code="telegram_entity_too_large",
                message="Telegram rejected an oversized entity",
            )
        except (TelegramForbiddenError, TelegramNotFound):
            return ProviderDeliveryResult.permanent_failure(
                category="recipient",
                code="telegram_recipient_unavailable",
                message="Telegram recipient is unavailable",
            )
        except TelegramMigrateToChat:
            return ProviderDeliveryResult.permanent_failure(
                category="recipient",
                code="telegram_chat_migrated",
                message="Telegram destination migrated and requires manual reconciliation",
            )
        except TelegramBadRequest:
            return ProviderDeliveryResult.permanent_failure(
                category="payload",
                code="telegram_bad_request",
                message="Telegram rejected the delivery request",
            )
        except (TelegramUnauthorizedError, TelegramConflictError):
            return ProviderDeliveryResult.permanent_failure(
                category="provider",
                code="telegram_provider_auth_or_conflict",
                message="Telegram provider authentication or ownership is unavailable",
            )
        except (TelegramNetworkError, TelegramServerError, TimeoutError):
            return ProviderDeliveryResult.ambiguous_failure(
                category="network",
                code="telegram_network_error",
                message=(
                    "Telegram network outcome requires manual reconciliation"
                ),
            )
        except TelegramAPIError:
            return ProviderDeliveryResult.ambiguous_failure(
                category="provider",
                code="telegram_api_error",
                message="Telegram API outcome requires manual reconciliation",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Exception strings from HTTP clients can include a bot-token URL.
            logger.warning(
                "Telegram delivery provider failed delivery_id=%s error_type=%s",
                normalized_delivery_id,
                type(exc).__name__,
            )
            return ProviderDeliveryResult.ambiguous_failure(
                category="provider",
                code="telegram_unexpected_error",
                message="Telegram provider outcome requires manual reconciliation",
            )

    async def _deliver(self, chat_id: int, text: str, options: TelegramMessageOptions | None):
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        thread_id = None
        if options is not None:
            params["reply_markup"] = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=label, url=url) for label, url in options.buttons
            ]])
            params["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
            if options.edit_message_id:
                edited = True
                try:
                    await self._bot.edit_message_text(message_id=options.edit_message_id, **params)
                except TelegramBadRequest as exc:
                    reason = exc.message.casefold()
                    edited = "message is not modified" in reason
                    if not edited and (options.edit_only or all(
                        error not in reason for error in ("message to edit not found", "message can't be edited")
                    )):
                        raise
                if options.edit_only:
                    return options.edit_message_id
                if edited and options.alert_text:
                    params["text"] = options.alert_text
                    params["reply_parameters"] = ReplyParameters(
                        message_id=options.edit_message_id, allow_sending_without_reply=True,
                    )
            params["disable_notification"] = options.silent
            if options.tender_topic:
                thread_id = settings.TELEGRAM_TENDER_TOPIC_IDS.get(chat_id)
        if thread_id:
            try:
                message = await self._bot.send_message(message_thread_id=thread_id, **params)
            except TelegramBadRequest as exc:
                reason = exc.message.casefold()
                if not any(error in reason for error in ("message thread not found", "topic_closed", "topic is closed", "chat is not a forum")):
                    raise
                params.pop("reply_parameters", None)
            else:
                return message.message_id
        return (await self._bot.send_message(**params)).message_id
