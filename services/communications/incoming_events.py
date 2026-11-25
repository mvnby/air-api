"""Transactional new-request producers; callers invoke only on creation."""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, IntegrationOutboxEvent, Lead, Order
from models.leads_inbox import InboxTriageState
from services.communications.incoming_contracts import (
    TENANT_INCOMING_CREATED_EVENT,
    TENDER_RECOMMENDATION_VERSION,
    TENDER_REVIEW_VERSION,
    TenderCard,
    TenantIncomingCreatedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.tender_cards import email_tender_card, native_tender_card


def _bounded(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value).strip()[:limit] or None


def tender_event_id(order_id: int, version: int) -> str:
    key = IntegrationOutboxService.build_deduplication_key(
        event_type=TENANT_INCOMING_CREATED_EVENT, schema_version=1,
        aggregate_type="order", aggregate_id=str(order_id), aggregate_version=version,
        idempotency_key=None,
    )
    return IntegrationOutboxService.build_event_id(key)


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
        subject: str | None = None,
        tender: TenderCard | None = None,
        version: int = 1,
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
            subject=_bounded(subject, 300),
            tender=tender,
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_INCOMING_CREATED_EVENT,
            aggregate_type=entity_type,
            aggregate_id=entity.id,
            aggregate_version=version,
            payload=payload.model_dump(mode="json", exclude={
                key for key in ("subject", "tender") if getattr(payload, key) is None
            }),
            priority=20 if version == 1 else 21,
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
    async def enqueue_order(cls, session: AsyncSession, order: Order, *, attachment_texts=()) -> None:
        customer = await session.get(Customer, order.customer_id) if order.customer_id else None
        if customer is not None and customer.tenant_id != order.tenant_id:
            raise ValueError("Incoming customer scope is invalid")
        meta = order.technical_meta or {}
        provider = meta.get("belzakupki") or {}
        tender = provider.get("tender") or {}
        contacts = tender.get("contacts") or []
        contact = next((item for item in contacts if isinstance(item, dict)), {})
        request_text = meta.get("email_source_text") or order.comment or order.title or ""
        subject = meta.get("email_subject")
        card = None
        if tender and order.lead_source == "belzakupki":
            card = await asyncio.to_thread(native_tender_card, provider, order.title)
        elif order.lead_source == "email":
            card = await asyncio.to_thread(email_tender_card, subject, request_text, attachment_texts, summary=order.comment)
        await cls._enqueue(
            session, order,
            name=customer.name if customer else tender.get("customer_name"),
            phone=customer.phone if customer else contact.get("phone"),
            email=customer.email if customer else contact.get("email"),
            request_text=request_text,
            subject=subject,
            tender=card,
        )

    @classmethod
    async def enqueue_tender_document_update(
        cls, session: AsyncSession, order: Order, *, document_texts=(), review_reason: str | None = None,
    ) -> None:
        if order.linked_order_id is not None:
            return
        initial = await session.get(IntegrationOutboxEvent, tender_event_id(order.id, 1))
        if initial is None or (initial.payload.get("tender") or {}).get("status") != "review":
            return
        if await session.get(IntegrationOutboxEvent, tender_event_id(order.id, TENDER_RECOMMENDATION_VERSION)):
            return
        provider = (order.technical_meta or {}).get("belzakupki") or {}
        if review_reason:
            original = TenderCard.model_validate(initial.payload["tender"])
            card = original.model_copy(update={"reason": review_reason})
            version = TENDER_REVIEW_VERSION
            if await session.get(IntegrationOutboxEvent, tender_event_id(order.id, version)):
                return
        else:
            card = await asyncio.to_thread(native_tender_card, provider, order.title, document_texts=document_texts)
            version = TENDER_RECOMMENDATION_VERSION
            if card.status != "recommend":
                return
        archived = await session.scalar(select(InboxTriageState.archived_at).where(
            InboxTriageState.entity_kind == "order", InboxTriageState.entity_id == order.id,
            InboxTriageState.tenant_id == order.tenant_id, InboxTriageState.storefront_id == order.storefront_id,
        ))
        if archived is not None:
            return
        await cls._enqueue(
            session, order, version=version, name=initial.payload.get("name"),
            phone=initial.payload.get("phone"), email=initial.payload.get("email"),
            tender=card.model_copy(update={"prior_event_id": initial.event_id}),
        )
