"""Authorized API orchestration for customer requisites received from Telegram."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.bot import BotCustomerRequisitesEditFields
from models import Customer, CustomerRequisitesRecognition
from models.tenancy import TenantScope
from services.bot_access_service import BotAccessService
from services.customer_creation_service import CustomerAlreadyExistsError
from services.customer_requisites_confirmation_service import CustomerRequisitesConfirmationService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.customer_requisites_review import TELEGRAM_SOURCES, review_revision
from services.customer_service import CustomerService
from services.tenant_scope_service import tenant_scope_clause


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
    async def _require_manager(
        session: AsyncSession, telegram_id: int, tenant_scope: TenantScope,
    ) -> None:
        context = await BotAccessService.get_context(session, telegram_id)
        selection = context.selection
        if (
            not context.is_staff or not context.is_manager or selection is None
            or selection.tenant_id != tenant_scope.tenant_id
            or selection.storefront_id != tenant_scope.storefront_id
        ):
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
        tenant_scope: TenantScope,
    ) -> None:
        if telegram_chat_id is None or telegram_message_id is None:
            return
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        lock_key = (
            f"bot-requisites:{tenant_scope.tenant_id}:{source}:{telegram_user_id}:"
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
        tenant_scope: TenantScope,
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
                    tenant_scope_clause(
                        CustomerRequisitesRecognition,
                        tenant_scope,
                    ),
                )
                .limit(1)
            )
        ).scalars().first()

    @classmethod
    async def _existing_response(
        cls,
        session: AsyncSession,
        recognition: CustomerRequisitesRecognition,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        duplicate = await CustomerRequisitesRecognitionService._find_duplicate(
            session,
            (recognition.extracted_json or {}).get("inn"),
            tenant_scope=tenant_scope,
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
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        await cls._require_manager(session, telegram_id, tenant_scope)
        source = "telegram_text"
        await cls._lock_message(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
        existing = await cls._find_message_recognition(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
        if existing:
            return await cls._existing_response(
                session,
                existing,
                tenant_scope=tenant_scope,
            )
        try:
            return await CustomerRequisitesRecognitionService.recognize_text(
                session,
                text=text_value,
                source=source,
                tenant_scope=tenant_scope,
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
                tenant_scope=tenant_scope,
            )
            if not existing:
                raise
            return await cls._existing_response(
                session,
                existing,
                tenant_scope=tenant_scope,
            )

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
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        await cls._require_manager(session, telegram_id, tenant_scope)
        source = "telegram"
        await cls._lock_message(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
        existing = await cls._find_message_recognition(
            session,
            source=source,
            telegram_user_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
        if existing:
            return await cls._existing_response(
                session,
                existing,
                tenant_scope=tenant_scope,
            )
        try:
            return await CustomerRequisitesRecognitionService.recognize_bytes(
                session,
                content=content,
                filename=filename,
                mime_type=mime_type,
                source=source,
                tenant_scope=tenant_scope,
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
                tenant_scope=tenant_scope,
            )
            if not existing:
                raise
            return await cls._existing_response(
                session,
                existing,
                tenant_scope=tenant_scope,
            )

    @classmethod
    async def _owned_recognition(
        cls, session: AsyncSession, *, telegram_id: int, recognition_id: int,
        tenant_scope: TenantScope, for_update: bool = False,
    ) -> CustomerRequisitesRecognition:
        await cls._require_manager(session, telegram_id, tenant_scope)
        query = select(CustomerRequisitesRecognition).where(
            CustomerRequisitesRecognition.id == recognition_id,
            tenant_scope_clause(CustomerRequisitesRecognition, tenant_scope),
        ).execution_options(populate_existing=True)
        if for_update:
            query = query.with_for_update()
        recognition = (await session.execute(query)).scalars().first()
        if recognition is None:
            raise BotCustomerRequisitesNotFoundError("Черновик реквизитов не найден")
        if recognition.telegram_user_id != telegram_id or recognition.source not in TELEGRAM_SOURCES:
            raise BotCustomerRequisitesAccessDeniedError("Нет доступа к этому черновику реквизитов")
        return recognition

    @classmethod
    async def review_for_manager(
        cls, session: AsyncSession, *, telegram_id: int, recognition_id: int,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        recognition = await cls._owned_recognition(
            session, telegram_id=telegram_id, recognition_id=recognition_id,
            tenant_scope=tenant_scope,
        )
        return await cls._existing_response(session, recognition, tenant_scope=tenant_scope)

    @staticmethod
    def _check_revision(
        recognition: CustomerRequisitesRecognition, duplicate: Customer | None,
        expected_revision: str | None,
    ) -> str:
        current = review_revision(recognition, duplicate)
        if expected_revision == current:
            return current
        if expected_revision is None and recognition.review_edit_count == 0:
            # Old chat buttons carry no revision. Preserve their original preview,
            # including historical drafts without a duplicate or a stored snapshot.
            if recognition.status != CustomerRequisitesRecognitionService.STATUS_RECOGNIZED:
                return current
            if recognition.review_revision == current:
                return current
            if (
                recognition.review_revision is None
                and recognition.duplicate_customer_id is None
                and duplicate is None
            ):
                return current
        raise BotCustomerRequisitesConflictError("Черновик или клиент изменился. Откройте актуальный предпросмотр.")

    @classmethod
    async def edit_for_manager(
        cls, session: AsyncSession, *, telegram_id: int, recognition_id: int,
        tenant_scope: TenantScope, fields: BotCustomerRequisitesEditFields, expected_revision: str,
    ) -> dict[str, Any]:
        recognition = await cls._owned_recognition(
            session, telegram_id=telegram_id, recognition_id=recognition_id,
            tenant_scope=tenant_scope, for_update=True,
        )
        if recognition.status != CustomerRequisitesRecognitionService.STATUS_RECOGNIZED:
            raise BotCustomerRequisitesConflictError("Завершённый черновик нельзя изменить")
        previous = recognition.extracted_json or {}
        duplicate = await CustomerRequisitesRecognitionService._find_duplicate(
            session, previous.get("inn"), tenant_scope=tenant_scope,
        )
        cls._check_revision(recognition, duplicate, expected_revision)
        draft, flags = CustomerRequisitesConfirmationService._prepare_draft(
            recognition, fields.model_dump(exclude_unset=True),
        )
        if draft.get("inn") != previous.get("inn"):
            duplicate = await CustomerRequisitesRecognitionService._find_duplicate(
                session, draft.get("inn"), tenant_scope=tenant_scope,
            )
        duplicate_id = duplicate.id if duplicate else None
        if (
            draft != previous or flags != recognition.validation_flags
            or duplicate_id != recognition.duplicate_customer_id
        ):
            recognition.extracted_json = draft
            recognition.validation_flags = flags
            recognition.duplicate_customer_id = duplicate_id
            recognition.review_edit_count += 1
            recognition.review_revision = review_revision(recognition, duplicate)
            await session.commit()
        return CustomerRequisitesRecognitionService._recognition_response(recognition, duplicate)

    @classmethod
    async def apply_action_for_manager(
        cls, session: AsyncSession, *, telegram_id: int, recognition_id: int, action: str,
        tenant_scope: TenantScope, expected_revision: str | None = None,
    ) -> BotCustomerRequisitesActionResult:
        recognition = await cls._owned_recognition(
            session, telegram_id=telegram_id, recognition_id=recognition_id,
            tenant_scope=tenant_scope, for_update=True,
        )
        pending = recognition.status == CustomerRequisitesRecognitionService.STATUS_RECOGNIZED
        duplicate = await CustomerRequisitesRecognitionService._find_duplicate(
            session, (recognition.extracted_json or {}).get("inn"),
            tenant_scope=tenant_scope, for_update=pending,
        )
        revision = cls._check_revision(recognition, duplicate, expected_revision)
        if not pending:
            previous_action = recognition.confirmed_action if recognition.status == "confirmed" else "cancel"
            if action != previous_action:
                raise BotCustomerRequisitesConflictError("Черновик уже завершён другим действием")
            customer = None
            if recognition.confirmed_customer_id is not None:
                customer = await CustomerService.get_for_manager(
                    session=session, customer_id=recognition.confirmed_customer_id,
                    tenant_scope=tenant_scope,
                )
            return BotCustomerRequisitesActionResult(
                recognition=CustomerRequisitesRecognitionService._recognition_response(recognition, duplicate),
                customer=customer, changed=False,
            )

        if action == "cancel":
            recognition.review_revision = revision
            cancelled = await CustomerRequisitesRecognitionService.cancel(
                session, recognition_id=recognition_id, tenant_scope=tenant_scope,
            )
            return BotCustomerRequisitesActionResult(recognition=cancelled, customer=None, changed=True)

        target_id = duplicate.id if duplicate else None
        if action in {"update", "use"} and target_id is None:
            raise BotCustomerRequisitesConflictError("В этом черновике нет клиента с совпадающим УНП")
        if action == "create" and duplicate is not None:
            raise BotCustomerRequisitesConflictError("Клиент с таким УНП уже существует")

        if action == "use":
            customer = await CustomerService.get_for_manager(
                session=session, customer_id=target_id, tenant_scope=tenant_scope,
            )
            if customer is None:
                raise BotCustomerRequisitesNotFoundError("Найденный клиент больше не доступен")
            recognition.review_revision = revision
            recognition.duplicate_customer_id = target_id
            recognition.status = CustomerRequisitesRecognitionService.STATUS_CONFIRMED
            recognition.confirmed_action = action
            recognition.confirmed_customer_id = target_id
            recognition.confirmed_at = datetime.now()
            await session.commit()
            return BotCustomerRequisitesActionResult(
                recognition=CustomerRequisitesRecognitionService._recognition_response(recognition, duplicate),
                customer=customer, changed=True,
            )

        try:
            confirmed = await CustomerRequisitesRecognitionService.confirm(
                session, recognition_id=recognition_id, action=action, customer_id=target_id,
                source=recognition.source, reviewed_revision=revision, tenant_scope=tenant_scope,
            )
        except CustomerAlreadyExistsError as exc:
            raise BotCustomerRequisitesConflictError(str(exc)) from exc
        return BotCustomerRequisitesActionResult(
            recognition=confirmed["recognition"], customer=confirmed["customer"], changed=True,
        )
