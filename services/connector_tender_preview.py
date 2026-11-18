"""Project scoped Belzakupki detail into a bounded document/lot inventory."""

import asyncio
from mimetypes import guess_type
from urllib.parse import urlsplit

import httpx
from services.tender_source_reference import detail_for_reference, resolve_source_reference, tender_snapshot_for_reference

from core.config import settings
from schemas_connector_tender_review import TenderDocumentInfo, TenderLot, TenderSourcePreviewResult
from services.connector_tender_inbox import _public_source_url
from services.belzakupki_canonical_identity import canonical_procurement_url, canonical_tender_url
from services.belzakupki_customer_evidence import extract_customer_evidence
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_import_service import BelzakupkiImportService
from services.belzakupki_source_equipment_service import BelzakupkiSourceEquipmentService


def display(value, limit=500):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return str(value).strip()[:limit] or None


def _public_url(data, tender):
    for value in (data.get("source_url"), tender.get("url")):
        if url := canonical_procurement_url(value):
            return url
    return canonical_tender_url(tender) or _public_source_url(tender.get("url"))


def procedure_type(url):
    if url and urlsplit(url).hostname == "goszakupki.by":
        return urlsplit(url).path.strip("/").split("/", 1)[0]
    return None


def _doc_inventory(source_docs, originals):
    documents = {}
    valid = isinstance(source_docs, list)
    for doc in source_docs if valid else ():
        key = display(doc.get("id"), 301) if isinstance(doc, dict) else None
        if not key or len(key) > 300 or key in documents:
            valid = False
            continue
        filename = display(doc.get("name")) or key
        documents[key] = TenderDocumentInfo(
            document_id=key, filename=filename,
            mime_type=display(doc.get("mime_type"), 120) or guess_type(filename)[0],
            has_source_text=bool(doc.get("extracted_text")),
            source_text_truncated=bool(doc.get("extracted_text_truncated")),
            source_error="Источник сообщил об ошибке извлечения." if doc.get("extraction_error") or doc.get("error") else None,
        )
    for item in originals:
        if not item.document_id:
            valid = False
            continue
        row = documents.setdefault(item.document_id, TenderDocumentInfo(
            document_id=item.document_id, filename=item.name, mime_type=item.mime_type))
        row.saved_original = True
    return documents, valid


async def source_inventory(session, scope, order_id, source_reference=None):
    order = await BelzakupkiEnrichmentService._order(session, order_id, scope)
    identity = resolve_source_reference(order, source_reference)
    card = await BelzakupkiSourceEquipmentService.card(session, order_id=order_id, scope=scope, source_reference=source_reference)
    warnings = []
    try:
        data = await detail_for_reference(order, source_reference)
    except (httpx.HTTPError, TimeoutError, RuntimeError, ValueError):
        data = {}
        warnings.append("Свежая карточка источника недоступна. Показаны данные, сохранённые в Kitlane.")
    docs, complete = _doc_inventory(data.get("documents"), card.originals)
    if not complete:
        warnings.append("Полнота перечня оригиналов не подтверждена.")
    tender = tender_snapshot_for_reference(order, identity)
    if tender.get("claimed_canonical_url"):
        complete = False
        warnings.append("Источник указывает на другую каноническую процедуру. Проверьте публикацию вручную.")
    return order, tender, data, card, docs, complete, warnings


async def get_tender_source_preview(session, actor, inputs):
    order, tender, data, card, docs, complete, warnings = await source_inventory(
        session, actor.tenant_scope, inputs.order_id, inputs.source_reference)
    source, external_id = resolve_source_reference(order, inputs.source_reference)
    source_url = _public_url(data, tender)
    evidence = await asyncio.to_thread(extract_customer_evidence, data) if data else None
    submission = evidence.submission if evidence and evidence.submission.method != "unknown" else card.submission
    raw_lots = data.get("lots") or data.get("objects") or []
    if not isinstance(raw_lots, list):
        raw_lots = []
        warnings.append("Источник вернул неизвестный формат лотов.")
    offset = (inputs.page - 1) * inputs.limit
    end = offset + inputs.limit
    lots = []
    for raw in raw_lots[offset:end]:
        if not isinstance(raw, dict):
            warnings.append("Источник вернул лот без структурированных полей.")
            continue
        lots.append(TenderLot(number=display(raw.get("number") or raw.get("lot_number")),
                              title=display(raw.get("name") or raw.get("title"), 1000),
                              quantity=display(raw.get("quantity")), estimated_value=display(raw.get("estimated_value")),
                              execution_address=display(raw.get("execution_address") or raw.get("delivery_place")
                                                        or raw.get("address") or raw.get("location"))))
    addresses = [item.address for item in card.objects if item.address]
    addresses.extend(lot.execution_address for lot in lots if lot.execution_address)
    raw_deadline = data.get("deadline_at") if data.get("deadline_at") is not None else tender.get("deadline_at")
    deadline_at = BelzakupkiImportService._parse_datetime(raw_deadline)
    if raw_deadline and deadline_at is None:
        warnings.append("Невозможно определить срок с часовым поясом.")
    if not docs:
        warnings.append("Оригиналы ТЗ в карточке не найдены.")
    return TenderSourcePreviewResult(
        order_id=inputs.order_id, manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{inputs.order_id}",
        source=source, external_id=external_id, source_url=source_url,
        title=display(data.get("title") or tender.get("title") or order.title, 1000),
        customer=(evidence.customer.name if evidence else None) or display(tender.get("customer_name")),
        deadline_at=deadline_at, deadline_kind=display(data.get("deadline_kind") or tender.get("deadline_kind")),
        estimated_value=display(data.get("estimated_value") if data.get("estimated_value") is not None else tender.get("estimated_value")),
        currency=display(data.get("currency") or tender.get("currency"), 12), procedure_type=procedure_type(source_url),
        submission_method=submission.method, submission_email=submission.email,
        execution_addresses=list(dict.fromkeys(addresses)), lots=lots, total_lots=len(raw_lots),
        documents=sorted(docs.values(), key=lambda doc: doc.document_id)[offset:end],
        total_documents=len(docs), inventory_complete=complete, page=inputs.page,
        next_page=inputs.page + 1 if end < max(len(docs), len(raw_lots)) else None,
        warnings=list(dict.fromkeys(warnings)))
