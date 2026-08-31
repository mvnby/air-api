from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.input_validation import normalize_phone_digits
from models import Customer, CustomerType
from models.tenancy import TenantScope
from services.customer_party import (
    signing_mode_for_customer_type,
    valid_signing_modes_for_customer_type,
)
from services.customer_service import CustomerService
from services.tenant_scope_service import tenant_scope_clause


class CustomerAlreadyExistsError(ValueError):
    def __init__(
        self,
        *,
        customer_id: int,
        customer_name: str,
        matched_fields: tuple[str, ...],
    ) -> None:
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.matched_fields = matched_fields
        field_labels = {
            "inn": "УНП",
            "phone": "телефону",
            "email": "email",
        }
        matched = ", ".join(field_labels[field] for field in matched_fields)
        super().__init__(
            f"Клиент «{customer_name}» уже существует и совпадает по {matched}"
        )


class CustomerCreationService:
    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _validate_signing_mode(
        *, customer_type: CustomerType, signing_mode: str
    ) -> None:
        if signing_mode not in valid_signing_modes_for_customer_type(customer_type):
            raise ValueError("Режим подписания не соответствует типу клиента")

    @classmethod
    async def create_for_manager(
        cls,
        session: AsyncSession,
        *,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Имя клиента не может быть пустым")

        customer_type = CustomerType(
            str(payload.get("type") or CustomerType.individual.value).strip().lower()
        )
        signing_mode = str(payload.get("signing_mode") or "").strip().lower()
        if not signing_mode:
            signing_mode = signing_mode_for_customer_type(customer_type)
        cls._validate_signing_mode(
            customer_type=customer_type,
            signing_mode=signing_mode,
        )

        phone = cls._clean_optional(payload.get("phone"))
        email = cls._clean_optional(payload.get("email"))
        inn = cls._clean_optional(payload.get("inn"))
        duplicate = await cls._find_duplicate(
            session,
            phone=phone,
            email=email,
            inn=inn,
            tenant_scope=tenant_scope,
        )
        if duplicate is not None:
            existing, matched_fields = duplicate
            raise CustomerAlreadyExistsError(
                customer_id=int(existing.id or 0),
                customer_name=existing.name,
                matched_fields=matched_fields,
            )

        customer = Customer(
            tenant_id=tenant_scope.tenant_id,
            name=name,
            phone=phone or "",
            email=email,
            type=customer_type,
            inn=inn,
            kpp=cls._clean_optional(payload.get("kpp")),
            full_legal_name=cls._clean_optional(payload.get("full_legal_name")),
            legal_address=cls._clean_optional(payload.get("legal_address")),
            actual_address=cls._clean_optional(payload.get("actual_address")),
            city=cls._clean_optional(payload.get("city")),
            bank_name=cls._clean_optional(payload.get("bank_name")),
            bic=cls._clean_optional(payload.get("bic")),
            iban=cls._clean_optional(payload.get("iban")),
            signer_position=(
                cls._clean_optional(payload.get("signer_position")) or "директора"
            ),
            signer_name=cls._clean_optional(payload.get("signer_name")),
            acting_basis=(
                cls._clean_optional(payload.get("acting_basis")) or "Устава"
            ),
            signing_mode=signing_mode,
            is_favorite=bool(payload.get("is_favorite", False)),
        )
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        created = await CustomerService.get_for_manager(
            session=session,
            customer_id=int(customer.id or 0),
            tenant_scope=tenant_scope,
        )
        if created is None:
            raise RuntimeError("Созданный клиент не найден")
        return created

    @classmethod
    async def _find_duplicate(
        cls,
        session: AsyncSession,
        *,
        phone: Optional[str],
        email: Optional[str],
        inn: Optional[str],
        tenant_scope: TenantScope,
    ) -> Optional[tuple[Customer, tuple[str, ...]]]:
        normalized_phone = normalize_phone_digits(phone or "")
        normalized_email = str(email or "").strip().lower()
        normalized_inn = str(inn or "").strip()
        if not normalized_phone and not normalized_email and not normalized_inn:
            return None

        customers = (
            (
                await session.execute(
                    select(Customer).where(
                        tenant_scope_clause(Customer, tenant_scope)
                    )
                )
            )
            .scalars()
            .all()
        )
        matches: list[tuple[int, Customer, tuple[str, ...]]] = []
        for customer in customers:
            matched_fields: list[str] = []
            if normalized_inn and str(customer.inn or "").strip() == normalized_inn:
                matched_fields.append("inn")
            if (
                normalized_phone
                and normalize_phone_digits(customer.phone or "") == normalized_phone
            ):
                matched_fields.append("phone")
            if (
                normalized_email
                and str(customer.email or "").strip().lower() == normalized_email
            ):
                matched_fields.append("email")
            if matched_fields:
                priority = sum(
                    {"inn": 300, "phone": 200, "email": 100}[field]
                    for field in matched_fields
                )
                matches.append((priority, customer, tuple(matched_fields)))

        if not matches:
            return None
        matches.sort(
            key=lambda item: (item[0], int(item[1].id or 0)),
            reverse=True,
        )
        _, customer, matched_fields = matches[0]
        return customer, matched_fields
