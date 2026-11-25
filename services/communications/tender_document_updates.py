"""Recheck quiet Belzakupki cards against scoped source attachments."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import String, cast, exists, or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxTriageState
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, _source_identity
from services.communications.incoming_contracts import TENANT_INCOMING_CREATED_EVENT, TENDER_RECOMMENDATION_VERSION
from services.communications.incoming_events import IncomingEventService
from services.communications.tender_cards import MAX_TENDER_CARD_TEXT
from services.tender_document_reader import load_tender_document
from services.tender_source_reference import detail_for_reference, resolve_source_reference

logger = logging.getLogger(__name__)
CHECKED_AT = "telegram_tender_documents_checked_at"
NO_ATTACHMENTS = "Вложения пока недоступны"
PARTIAL_ATTACHMENTS = "Часть ТЗ требует сверки с оригиналом"
ATTACHMENT_LIMIT = "Вложения превышают лимит автопроверки"


@dataclass(frozen=True)
class TenderAttachmentCheck:
    texts: tuple[str, ...] = ()
    reason: str | None = None


def _source_references(order: Order) -> list[str | None]:
    provider = (order.technical_meta or {}).get("belzakupki") or {}
    entries = provider.get("source_references")
    if not isinstance(entries, dict):
        return [None]
    primary = _source_identity(order)
    canonical = provider.get("canonical_url")
    preferred, mirrors = [], []
    for key, entry in entries.items():
        try:
            if resolve_source_reference(order, key) == primary:
                continue
        except LookupError:
            continue
        (preferred if canonical and entry.get("url") == canonical else mirrors).append(key)
    return [*preferred, None, *mirrors]


async def _attachment_text(doc, *, order_id, scope, reference) -> str | None:
    text = doc.get("extracted_text")
    name = str(doc.get("name") or "")
    # PDF text from the source can omit scanned pages alongside a native text layer.
    if (not name.casefold().endswith(".pdf") and isinstance(text, str) and text.strip()
            and not doc.get("extracted_text_truncated")):
        return text
    async with async_session_maker() as session:
        result = await load_tender_document(
            session, scope, order_id=order_id, document_id=str(doc["id"]), source_reference=reference,
        )
    if result.status == "complete":
        return "".join(fragment.text for fragment in result.fragments)
    return None


async def _read_documents(order: Order, *, tenant_scope) -> TenderAttachmentCheck:
    try:
        async with asyncio.timeout(55):
            originals = {}
            for reference in _source_references(order):
                try:
                    detail = await detail_for_reference(order, reference)
                except (httpx.HTTPError, ValueError) as exc:
                    logger.info("Tender attachment check deferred order_id=%s error_type=%s", order.id, type(exc).__name__)
                    continue
                for doc in BelzakupkiEnrichmentService._documents(detail):
                    # The source document ID is derived from the original file name and URL.
                    originals.setdefault(str(doc["id"]), (reference, doc))
                if len(originals) > 8:
                    return TenderAttachmentCheck(reason=ATTACHMENT_LIMIT)
            if not originals:
                return TenderAttachmentCheck(reason=NO_ATTACHMENTS)
            texts = []
            used_chars = 0
            for reference, doc in originals.values():
                value = await _attachment_text(doc, order_id=order.id, scope=tenant_scope, reference=reference)
                if not value or not value.strip():
                    return TenderAttachmentCheck(reason=PARTIAL_ATTACHMENTS)
                used_chars += len(value)
                if used_chars > MAX_TENDER_CARD_TEXT:
                    return TenderAttachmentCheck(reason=ATTACHMENT_LIMIT)
                texts.append(value)
            return TenderAttachmentCheck(texts=tuple(texts))
    except TimeoutError:
        return TenderAttachmentCheck(reason=PARTIAL_ATTACHMENTS)


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
                    promoted.aggregate_version == TENDER_RECOMMENDATION_VERSION,
                ),
            ).order_by(checked_at.asc().nulls_first(), IntegrationOutboxEvent.occurred_at.asc()).limit(3)
        )).all()

    checks = await asyncio.gather(
        *(_read_documents(order, tenant_scope=tenant_scope) for order in orders), return_exceptions=True,
    )
    for scanned, check in zip(orders, checks, strict=True):
        if isinstance(check, asyncio.CancelledError):
            raise check
        if isinstance(check, BaseException):
            logger.warning("Tender attachment check failed order_id=%s error_type=%s", scanned.id, type(check).__name__)
            continue
        async with async_session_maker() as session:
            order = await session.scalar(select(Order).where(*active, Order.id == scanned.id).with_for_update())
            if order is None:
                continue
            original_source = (scanned.technical_meta or {}).get("belzakupki")
            if original_source != (order.technical_meta or {}).get("belzakupki"):
                continue
            await IncomingEventService.enqueue_tender_document_update(
                session, order, document_texts=check.texts, review_reason=check.reason,
            )
            order.technical_meta = {**(order.technical_meta or {}), CHECKED_AT: now.isoformat()}
            flag_modified(order, "technical_meta")
            await session.commit()
