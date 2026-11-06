"""Transactional new-request producers; callers invoke only on creation."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Lead, Order
from services.communications.incoming_contracts import (
    TENANT_INCOMING_CREATED_EVENT,
    TenantIncomingCreatedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService


def _bounded(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value).strip()[:limit] or None


class IncomingEventService:
    @staticmethod
    async def _enqueue(
        session: AsyncSession,
        entity: Lead | Order,
        *,
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        request_text: str = "",
    ) -> None:
        entity_type = "lead" if isinstance(entity, Lead) else "order"
        source = entity.source if entity_type == "lead" else entity.lead_source
        payload = TenantIncomingCreatedPayloadV1(
            tenant_id=entity.tenant_id,
            storefront_id=entity.storefront_id,
            entity_type=entity_type,
            entity_id=entity.id,
            source=source.value if hasattr(source, "value") else str(source),
            name=_bounded(name, 240),
            phone=_bounded(phone, 100),
            email=_bounded(email, 254),
            request_text=_bounded(request_text, 12000) or "",
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_INCOMING_CREATED_EVENT,
            aggregate_type=entity_type,
            aggregate_id=entity.id,
            aggregate_version=1,
            payload=payload,
            priority=20,
            max_attempts=8,
        )

    @classmethod
    async def enqueue_lead(cls, session: AsyncSession, lead: Lead) -> None:
        await cls._enqueue(
            session, lead,
            name=lead.company_name or lead.name,
            phone=lead.phone,
            email=lead.email,
            request_text=lead.request_text,
        )

    @classmethod
    async def enqueue_order(cls, session: AsyncSession, order: Order) -> None:
        customer = await session.get(Customer, order.customer_id) if order.customer_id else None
        if customer is not None and customer.tenant_id != order.tenant_id:
            raise ValueError("Incoming customer scope is invalid")
        meta = order.technical_meta or {}
        tender = (meta.get("belzakupki") or {}).get("tender") or {}
        contacts = tender.get("contacts") or []
        contact = next((item for item in contacts if isinstance(item, dict)), {})
        request_text = meta.get("email_source_text") or order.comment or order.title or ""
        if meta.get("email_subject"):
            request_text = f"Тема письма: {meta['email_subject']}\n\n{request_text}"
        await cls._enqueue(
            session, order,
            name=customer.name if customer else tender.get("customer_name"),
            phone=customer.phone if customer else contact.get("phone"),
            email=customer.email if customer else contact.get("email"),
            request_text=request_text,
        )
