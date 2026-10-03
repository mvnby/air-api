"""Apply a reviewed requisites draft to a customer in one transaction."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerRequisitesRecognition, CustomerType
from models.tenancy import TenantScope
from services.customer_creation_service import (
    CustomerAlreadyExistsError,
    CustomerCreationService,
)
from services.customer_contact_service import CustomerContactService
from services.customer_party import (
    signing_mode_for_customer_type,
    valid_signing_modes_for_customer_type,
)
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService as Recognition
from services.customer_service import CustomerService
from services.tenant_scope_service import tenant_scope_clause


class CustomerRequisitesConflictError(ValueError):
    """The draft was consumed or the target changed after review."""


class CustomerRequisitesConfirmationService:
    EDITABLE_FIELDS = frozenset({
        "name", "full_legal_name", "customer_type", "inn", "legal_address",
        "bank_name", "bic", "iban", "email", "phone", "signer_position",
        "signer_name", "acting_basis",
    })
    CUSTOMER_FIELDS = {"customer_type": "type"}

    @classmethod
    async def _response(
        cls,
        session: AsyncSession,
        recognition: CustomerRequisitesRecognition,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        customer_data = await CustomerService.get_for_manager(
            session=session,
            customer_id=int(recognition.confirmed_customer_id or 0),
            tenant_scope=tenant_scope,
        )
        if customer_data is None:
            raise LookupError("Customer not found")
        duplicate = await Recognition._find_duplicate(
            session, (recognition.extracted_json or {}).get("inn"),
            phone=(recognition.extracted_json or {}).get("phone") if recognition.source == "manager" else None,
            email=(recognition.extracted_json or {}).get("email") if recognition.source == "manager" else None,
            tenant_scope=tenant_scope,
        )
        return {
            "recognition": Recognition._recognition_response(recognition, duplicate),
            "customer": customer_data,
        }

    @staticmethod
    def _db_value(customer: Customer, field: str) -> Optional[str]:
        attribute = "type" if field == "customer_type" else field
        value = getattr(customer, attribute)
        if isinstance(value, CustomerType):
            return value.value
        return str(value) if value is not None else None

    @classmethod
    def _check_baseline(
        cls,
        customer: Customer,
        fields: set[str],
        baseline: Optional[dict[str, Optional[str]]],
    ) -> None:
        if baseline is None:
            return
        if not fields.issubset(baseline):
            raise ValueError("Для выбранных полей нужны исходные значения клиента")
        stale = sorted(
            field for field in fields
            if cls._db_value(customer, field) != baseline[field]
        )
        if stale:
            raise CustomerRequisitesConflictError(
                "Клиент изменился после открытия черновика: " + ", ".join(stale)
            )

    @classmethod
    def _prepare_draft(
        cls,
        recognition: CustomerRequisitesRecognition,
        corrections: Optional[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        draft = dict(recognition.extracted_json or {})
        if corrections:
            unexpected = set(corrections) - cls.EDITABLE_FIELDS - {"phone_raw", "extra"}
            if unexpected:
                raise ValueError("Неизвестные поля реквизитов: " + ", ".join(sorted(unexpected)))
            draft.update(corrections)
            if "phone" in corrections:
                draft["phone_raw"] = corrections["phone"]
        normalized, flags = Recognition._normalize_extracted(draft, recognition.raw_text)
        if corrections:
            for field in corrections:
                if field in cls.EDITABLE_FIELDS and corrections[field] in (None, ""):
                    normalized[field] = None
                    if field == "name":
                        flags["field_errors"]["name"] = "Название клиента не может быть пустым"
            if "phone" in corrections and corrections["phone"] and not normalized["phone"]:
                flags["field_errors"]["phone"] = "Некорректный номер телефона"
        return normalized, flags

    @classmethod
    async def confirm(
        cls,
        session: AsyncSession,
        *,
        recognition_id: int,
        action: str,
        customer_id: Optional[int],
        extracted: Optional[dict[str, Any]],
        selected_fields: Optional[list[str]],
        baseline: Optional[dict[str, Optional[str]]],
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"create", "update"}:
            raise ValueError("action must be create or update")
        recognition = (
            await session.execute(
                select(CustomerRequisitesRecognition).where(
                    CustomerRequisitesRecognition.id == recognition_id,
                    tenant_scope_clause(CustomerRequisitesRecognition, tenant_scope),
                ).with_for_update()
            )
        ).scalars().first()
        if recognition is None:
            raise LookupError("Recognition not found")
        if recognition.status == Recognition.STATUS_CONFIRMED:
            if (
                recognition.confirmed_action == normalized_action
                and (customer_id is None or customer_id == recognition.confirmed_customer_id)
            ):
                return await cls._response(session, recognition, tenant_scope=tenant_scope)
            raise CustomerRequisitesConflictError("Распознавание уже подтверждено другим действием")
        if recognition.status != Recognition.STATUS_RECOGNIZED:
            raise CustomerRequisitesConflictError("Распознавание больше нельзя подтвердить")

        fields = set(selected_fields or ())
        if selected_fields is not None and (not fields or fields - cls.EDITABLE_FIELDS):
            raise ValueError("Выберите допустимые поля для сохранения")
        if normalized_action == "create" and selected_fields is not None and "name" not in fields:
            raise ValueError("Для нового клиента выберите название")
        if normalized_action == "update" and selected_fields is not None and baseline is None:
            raise ValueError("Для обновления нужны исходные значения выбранных полей")
        if extracted and selected_fields is not None and set(extracted) - fields - {"phone_raw", "extra"}:
            raise ValueError("Исправлены поля, которые не выбраны для сохранения")
        draft, flags = cls._prepare_draft(recognition, extracted)
        if selected_fields is None:
            # Existing Telegram actions and old Manager clients keep their
            # historical default: apply recognized, nonempty values.
            fields = {field for field in cls.EDITABLE_FIELDS if draft.get(field) not in {None, ""}}
        errors = flags.get("field_errors") or {}
        blocking = errors if normalized_action == "create" and selected_fields is None else {
            field: message for field, message in errors.items() if field in fields
        }
        if blocking:
            raise ValueError("Исправьте ошибки реквизитов: " + ", ".join(sorted(blocking)))

        if normalized_action == "create":
            create_draft = draft if selected_fields is None else {
                field: value for field, value in draft.items() if field in fields
            }
            payload = Recognition._customer_payload(create_draft, raw_text=recognition.raw_text)
            if selected_fields is not None:
                for field in cls.EDITABLE_FIELDS - fields:
                    if field in {"customer_type", "name"}:
                        continue
                    payload[cls.CUSTOMER_FIELDS.get(field, field)] = "" if field == "phone" else None
            customer = await CustomerCreationService.create_record_for_manager(
                session, payload=payload, tenant_scope=tenant_scope,
            )
        else:
            target_id = customer_id
            if target_id is None and recognition.duplicate_customer_id and draft.get("inn"):
                # Phone and email matches are suggestions only. Never merge
                # a requisites sheet into a company on those signals alone.
                candidate = await session.get(Customer, recognition.duplicate_customer_id)
                if candidate and candidate.inn == draft["inn"]:
                    target_id = candidate.id
            if target_id is None:
                raise ValueError("Не выбран клиент для обновления")
            customer = (
                await session.execute(select(Customer).where(
                    Customer.id == int(target_id),
                    tenant_scope_clause(Customer, tenant_scope),
                ).with_for_update())
            ).scalars().first()
            if customer is None:
                raise LookupError("Customer not found")
            cls._check_baseline(customer, fields, baseline)
            if "inn" in fields and draft.get("inn"):
                same_inn = await CustomerCreationService._find_duplicate(
                    session, inn=draft["inn"], phone=None, email=None,
                    tenant_scope=tenant_scope,
                )
                if same_inn and same_inn[0].id != customer.id:
                    matched = same_inn[0]
                    raise CustomerAlreadyExistsError(
                        customer_id=int(matched.id or 0),
                        customer_name=matched.name,
                        matched_fields=("inn",),
                    )
            for field in fields:
                value = draft.get(field)
                if field in {"name", "customer_type", "signer_position", "acting_basis"} and not value:
                    raise ValueError(f"Поле {field} не может быть пустым")
                if field == "customer_type":
                    customer.type = CustomerType(value)
                elif field == "phone":
                    customer.phone = value or ""
                else:
                    setattr(customer, field, value)
            if "customer_type" in fields and customer.signing_mode not in valid_signing_modes_for_customer_type(customer.type):
                customer.signing_mode = signing_mode_for_customer_type(customer.type)
            if fields & {"phone", "email"}:
                await CustomerContactService.sync_primary_fields(
                    session, customer, phone=customer.phone, email=customer.email,
                )
            session.add(customer)
            await session.flush()

        recognition.extracted_json = draft
        recognition.validation_flags = flags
        recognition.status = Recognition.STATUS_CONFIRMED
        recognition.confirmed_action = normalized_action
        recognition.confirmed_customer_id = customer.id
        recognition.confirmed_at = datetime.now()
        session.add(recognition)
        await session.commit()
        await session.refresh(recognition)
        return await cls._response(session, recognition, tenant_scope=tenant_scope)
