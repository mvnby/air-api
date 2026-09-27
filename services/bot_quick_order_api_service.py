"""Authorized API orchestration for Telegram quick-order use cases."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from api_contracts.bot import BotQuickOrderDraft
from models import Order
from services.bot_access_service import BotAccessService
from services.bot_quick_order_service import BotQuickOrderService
from services.order_scenarios import WORKFLOW_LABELS
from services.tenant_scope_service import SystemTenantScopeResolver


class BotQuickOrderAccessDeniedError(PermissionError):
    pass


@dataclass(frozen=True)
class BotQuickOrderCreateResult:
    order_id: int
    customer_id: int
    created: bool


class BotQuickOrderApiService:
    @staticmethod
    async def _create_locked(
        session: AsyncSession,
        *,
        telegram_id: int,
        source_fingerprint: str,
        draft: BotQuickOrderDraft,
    ) -> BotQuickOrderCreateResult:
        await BotQuickOrderApiService._require_manager(session, telegram_id)
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        order_data = await BotQuickOrderService.create_order_from_draft(
            session,
            draft.model_dump(mode="json", exclude={"service_label"}),
            source_fingerprint=source_fingerprint,
            tenant_scope=tenant_scope,
        )
        order_id = int(order_data.get("id") or 0)
        if not order_id:
            raise ValueError("Не удалось определить созданный заказ")

        customer = order_data.get("customer") if isinstance(order_data.get("customer"), dict) else {}
        customer_id = int(customer.get("id") or order_data.get("customer_id") or 0)
        if not customer_id:
            order = await session.get(Order, order_id)
            customer_id = int(order.customer_id or 0) if order else 0
        if not customer_id:
            raise ValueError("Не удалось определить клиента заказа")

        return BotQuickOrderCreateResult(
            order_id=order_id,
            customer_id=customer_id,
            created=bool(order_data.get("_bot_order_created", True)),
        )

    @staticmethod
    async def _require_manager(session: AsyncSession, telegram_id: int) -> None:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff or not context.is_manager:
            raise BotQuickOrderAccessDeniedError("Manager quick-order access is required")

    @staticmethod
    def _request_fingerprint(*, telegram_id: int, idempotency_key: str) -> str:
        raw = f"v1:{telegram_id}:{idempotency_key}".encode("utf-8")
        return f"bot_quick_order:v1:{sha256(raw).hexdigest()}"

    @classmethod
    def _draft_projection(cls, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = BotQuickOrderService.normalize_draft(draft)
        service_type = normalized.get("service_type")
        parser = "ai" if str(normalized.get("parser") or "").strip() == "ai" else "fallback"
        address_check = normalized.get("address_check")
        if not isinstance(address_check, dict) or address_check.get("status") not in {
            "unchecked",
            "not_found",
            "needs_review",
            "confirmed",
        }:
            address_check = None
        return {
            "customer_id": normalized.get("customer_id"),
            "customer_type": normalized.get("customer_type"),
            "name": normalized.get("name"),
            "contact_name": normalized.get("contact_name"),
            "contact_phone": normalized.get("contact_phone"),
            "contact_email": normalized.get("contact_email"),
            "phone": normalized.get("phone"),
            "email": normalized.get("email"),
            "inn": normalized.get("inn"),
            "customer_branch_id": normalized.get("customer_branch_id"),
            "address": normalized.get("address"),
            "legal_address": normalized.get("legal_address"),
            "workflow_type": normalized.get("workflow_type"),
            "service_type": service_type,
            "service_label": BotQuickOrderService.SERVICE_LABELS.get(service_type, WORKFLOW_LABELS.get(normalized.get("workflow_type"), "Не указана")),
            "target_date": normalized.get("target_date"),
            "target_date_precision": normalized.get("target_date_precision"),
            "equipment_summary": normalized.get("equipment_summary"),
            "equipment_count": normalized.get("equipment_count"),
            "equipment_type": normalized.get("equipment_type"),
            "field_sources": normalized.get("field_sources") or {},
            "request_text": normalized.get("request_text") or "Быстрый заказ из Telegram",
            "parser": parser,
            "address_check": address_check,
        }

    @classmethod
    async def parse_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        text: str,
    ) -> dict[str, Any]:
        await cls._require_manager(session, telegram_id)
        return cls._draft_projection(await BotQuickOrderService.parse_text(text))

    @classmethod
    async def create_for_manager(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        idempotency_key: str,
        draft: BotQuickOrderDraft,
    ) -> BotQuickOrderCreateResult:
        source_fingerprint = cls._request_fingerprint(
            telegram_id=telegram_id,
            idempotency_key=idempotency_key,
        )
        bind = session.bind
        if not isinstance(bind, AsyncEngine) or bind.dialect.name != "postgresql":
            return await cls._create_locked(
                session,
                telegram_id=telegram_id,
                source_fingerprint=source_fingerprint,
                draft=draft,
            )

        lock_key = f"bot-quick-order:{source_fingerprint}"
        async with bind.connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(hashtext(:lock_key)::bigint)"),
                {"lock_key": lock_key},
            )
            await connection.commit()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as locked_session:
                    return await cls._create_locked(
                        locked_session,
                        telegram_id=telegram_id,
                        source_fingerprint=source_fingerprint,
                        draft=draft,
                    )
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:lock_key)::bigint)"),
                    {"lock_key": lock_key},
                )
                await connection.commit()
