"""Recheck quiet Belzakupki cards against available source attachment text."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import String, cast, exists, or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxTriageState
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.communications.incoming_contracts import TENANT_INCOMING_CREATED_EVENT
from services.communications.incoming_events import IncomingEventService

logger = logging.getLogger(__name__)
CHECKED_AT = "telegram_tender_documents_checked_at"


async def _read_documents(order: Order) -> tuple[str, ...]:
    try:
        detail = await BelzakupkiEnrichmentService._detail(order)
        documents = BelzakupkiEnrichmentService._documents(detail)
        if not 1 <= len(documents) <= 8:
            return ()
        if any(
            not isinstance(doc.get("extracted_text"), str) or not doc["extracted_text"].strip()
            or len(doc["extracted_text"]) > 16000 or doc.get("extracted_text_truncated")
            for doc in documents
        ):
            return ()
        return tuple(doc["extracted_text"] for doc in documents)
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Tender attachment check deferred order_id=%s error_type=%s", order.id, type(exc).__name__)
        return ()


async def refresh_tender_cards(*, tenant_scope) -> None:
    now = datetime.now(timezone.utc)
    order_id = cast(Order.id, String)
    checked_at = Order.technical_meta[CHECKED_AT].as_string()
    promoted = aliased(IntegrationOutboxEvent)
    active = (
        Order.tenant_id == tenant_scope.tenant_id,
        Order.storefront_id == tenant_scope.storefront_id,
        Order.lead_source == LeadSource.BELZAKUPKI,
        Order.status == OrderStatus.NEW_LEAD,
        Order.linked_order_id.is_(None),
        ~exists().where(
            InboxTriageState.entity_kind == "order",
            InboxTriageState.entity_id == Order.id,
            InboxTriageState.tenant_id == tenant_scope.tenant_id,
            InboxTriageState.storefront_id == tenant_scope.storefront_id,
            InboxTriageState.archived_at.is_not(None),
        ),
    )
    async with async_session_maker() as session:
        orders = (await session.scalars(
            select(Order).join(IntegrationOutboxEvent, IntegrationOutboxEvent.aggregate_id == order_id)
            .where(
                *active,
                IntegrationOutboxEvent.event_type == TENANT_INCOMING_CREATED_EVENT,
                IntegrationOutboxEvent.aggregate_type == "order",
                IntegrationOutboxEvent.aggregate_version == 1,
                IntegrationOutboxEvent.occurred_at >= now - timedelta(days=2),
                IntegrationOutboxEvent.payload["tender"]["status"].as_string() == "review",
                or_(checked_at.is_(None), checked_at < (now - timedelta(minutes=30)).isoformat()),
                ~exists().where(
                    promoted.event_type == TENANT_INCOMING_CREATED_EVENT,
                    promoted.aggregate_type == "order",
                    promoted.aggregate_id == order_id,
                    promoted.aggregate_version == 2,
                ),
            ).order_by(checked_at.asc().nulls_first(), IntegrationOutboxEvent.occurred_at.asc()).limit(3)
        )).all()

    texts = await asyncio.gather(*(_read_documents(order) for order in orders))
    for scanned, documents in zip(orders, texts, strict=True):
        async with async_session_maker() as session:
            order = await session.scalar(select(Order).where(*active, Order.id == scanned.id).with_for_update())
            if order is None:
                continue
            original_source = (scanned.technical_meta or {}).get("belzakupki")
            if original_source != (order.technical_meta or {}).get("belzakupki"):
                continue
            if documents:
                await IncomingEventService.enqueue_tender_recommendation(session, order, document_texts=documents)
            order.technical_meta = {**(order.technical_meta or {}), CHECKED_AT: now.isoformat()}
            flag_modified(order, "technical_meta")
            await session.commit()
