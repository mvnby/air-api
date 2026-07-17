"""Authorized API orchestration for customer requisites received from Telegram."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CustomerRequisitesRecognition
from services.bot_access_service import BotAccessService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.customer_service import CustomerService


class BotCustomerRequisitesAccessDeniedError(PermissionError):
    pass


class BotCustomerRequisitesNotFoundError(LookupError):
    pass


class BotCustomerRequisitesConflictError(ValueError):
    pass


@dataclass(frozen=True)
class BotCustomerRequisitesActionResult:
    recognition: dict[str, Any]
    customer: dict[str, Any] | None
    changed: bool


class BotCustomerRequisitesApiService:
    @staticmethod
    async def _require_manager(session: AsyncSession, telegram_id: int) -> None:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff or not context.is_manager:
            raise BotCustomerRequisitesAccessDeniedError(
                "Manager customer requisites access is required"
            )

    @staticmethod
    async def _lock_message(
        session: AsyncSession,
        *,
        source: str,
        telegram_user_id: int,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        if telegram_chat_id is None or telegram_message_id is None:
            return
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        lock_key = (
            f"bot-requisites:{source}:{telegram_user_id}:"
            f"{telegram_chat_id}:{telegram_message_id}"
        )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
            {"lock_key": lock_key},
        )

    @staticmethod
    async def _find_message_recognition(
        session: AsyncSession,
        *,
        source: str,
        telegram_user_id: int,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> CustomerRequisitesRecognition | None:
        if telegram_chat_id is None or telegram_message_id is None:
            return None
        return (
            await session.execute(
                select(CustomerRequisitesRecognition)
                .where(
                    CustomerRequisitesRecognition.source == source,
                    CustomerRequisitesRecognition.telegram_user_id == telegram_user_id,
                    CustomerRequisitesRecognition.telegram_chat_id == telegram_chat_id,
                    CustomerRequisitesRecognition.telegram_message_id == telegram_message_id,
                )
                .limit(1)
            )
        ).scalars().first()

    @classmethod
    async def _existing_response(
        cls,
        session: AsyncSession,
        recognition: CustomerRequisitesRecognition,
    ) -> dict[str, Any]:
        duplicate = await CustomerRequisitesRecognitionService._find_duplicate(
            session,
            (recognition.extracted_json or {}).get("inn"),
        )
        return CustomerRequisitesRecognitionService._recognition_response(
            recognition,
            duplicate,
        )

    @classmethod
    async def recognize_text_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        text_value: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any]:
        await cls._require_manager(session, telegram_id)
        source = "telegram_text"
        await cls._lock_message(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        existing = await cls._find_message_recognition(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        if existing:
            return await cls._existing_response(session, existing)
        try:
            return await CustomerRequisitesRecognitionService.recognize_text(
                session,
                text=text_value,
                source=source,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
        except IntegrityError:
            await session.rollback()
            existing = await cls._find_message_recognition(
                session,
                source=source,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
            if not existing:
                raise
            return await cls._existing_response(session, existing)

    @classmethod
    async def recognize_file_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        content: bytes,
        filename: str,
        mime_type: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> dict[str, Any]:
        await cls._require_manager(session, telegram_id)
        source = "telegram"
        await cls._lock_message(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        existing = await cls._find_message_recognition(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        if existing:
            return await cls._existing_response(session, existing)
        try:
            return await CustomerRequisitesRecognitionService.recognize_bytes(
                session,
                content=content,
                filename=filename,
                mime_type=mime_type,
                source=source,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
        except IntegrityError:
            await session.rollback()
            existing = await cls._find_message_recognition(
                session,
                source=source,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
            if not existing:
                raise
            return await cls._existing_response(session, existing)

    @classmethod
    async def apply_action_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        recognition_id: int,
        action: str,
    ) -> BotCustomerRequisitesActionResult:
        await cls._require_manager(session, telegram_id)
        recognition = (
            await session.execute(
                select(CustomerRequisitesRecognition)
                .where(CustomerRequisitesRecognition.id == recognition_id)
                .with_for_update()
            )
        ).scalars().first()
        if not recognition:
            raise BotCustomerRequisitesNotFoundError("Recognition not found")
        if recognition.telegram_user_id not in {None, telegram_id}:
            raise BotCustomerRequisitesAccessDeniedError(
                "Recognition belongs to another Telegram user"
            )

        if recognition.status == CustomerRequisitesRecognitionService.STATUS_CONFIRMED:
            if action != recognition.confirmed_action:
                raise BotCustomerRequisitesConflictError(
                    "Recognition was already confirmed with another action"
                )
            customer = await CustomerService.get_for_manager(
                session=session,
                customer_id=int(recognition.confirmed_customer_id or 0),
            )
            return BotCustomerRequisitesActionResult(
                recognition=await cls._existing_response(session, recognition),
                customer=customer,
                changed=False,
            )

        if recognition.status == CustomerRequisitesRecognitionService.STATUS_CANCELLED:
            if action != "cancel":
                raise BotCustomerRequisitesConflictError("Recognition was already cancelled")
            return BotCustomerRequisitesActionResult(
                recognition=await cls._existing_response(session, recognition),
                customer=None,
                changed=False,
            )

        if action == "cancel":
            cancelled = await CustomerRequisitesRecognitionService.cancel(
                session,
                recognition_id=recognition_id,
            )
            return BotCustomerRequisitesActionResult(
                recognition=cancelled,
                customer=None,
                changed=True,
            )

        confirmed = await CustomerRequisitesRecognitionService.confirm(
            session,
            recognition_id=recognition_id,
            action=action,
        )
        return BotCustomerRequisitesActionResult(
            recognition=confirmed["recognition"],
            customer=confirmed["customer"],
            changed=True,
        )
