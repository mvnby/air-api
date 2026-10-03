"""Explicit, read-only inspection of legacy originals for reconciliation review."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import hashlib
import re

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CustomerContract, Order, OrderDocument
from models.tenancy import TenantScope
from schemas_manager_orders import ManagerLegacyReconciliationConfirmPayload
from services.google_service import get_google_service
from services.tenant_scope_service import storefront_scope_clause


LEGACY_META_KEY = "reconciliation_legacy_confirmation"
MAX_SOURCE_CHARS = 100_000
DOCUMENT_LABELS = {
    "act": r"акт(?:а)?",
    "service_act": r"акт(?:а)?",
    "maintenance_service_act": r"акт(?:а)?",
    "tn2": r"тн[- ]?2",
    "ttn1": r"ттн[- ]?1",
    "retail_receipt": r"(?:товарный\s+)?чек",
}
RUSSIAN_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
DATE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"
    r"|(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"
    r"|(?<!\d)[«\"„]?\s*(\d{1,2})\s*[»\"“]?\s+"
    r"(" + "|".join(RUSSIAN_MONTHS) + r")\s+(\d{4})\s*(?:г\.?|года)?",
    re.I,
)


class LegacyDocumentReviewError(ValueError):
    pass


async def _load_document(
    session: AsyncSession, customer_id: int, document_id: int, scope: TenantScope,
    *, lock: bool = False,
) -> OrderDocument | None:
    statement = (
        select(OrderDocument)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            OrderDocument.id == document_id,
            Order.customer_id == customer_id,
            storefront_scope_clause(Order, scope),
        )
    )
    if lock:
        statement = statement.with_for_update(of=OrderDocument)
    return (await session.execute(statement)).scalar_one_or_none()


def _text_from_google(file_id: str) -> str:
    service = get_google_service()
    try:
        payload = service.export_file(file_id, mime_type="text/plain").getvalue()
    except Exception:
        # Legacy paper waybills were sometimes Google Sheets.
        payload = service.export_file(file_id, mime_type="text/csv").getvalue()
    if len(payload) > 400_000:
        raise LegacyDocumentReviewError("Оригинал слишком большой для проверки")
    text = payload.decode("utf-8-sig", errors="replace").strip()
    if not text or len(text) > MAX_SOURCE_CHARS:
        raise LegacyDocumentReviewError("Текст оригинала пуст или слишком большой")
    return text


def _dates_in_text(text: str) -> list[tuple[date, int]]:
    found: list[tuple[date, int]] = []
    for match in DATE_PATTERN.finditer(text):
        try:
            if match.group(1):
                value = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            elif match.group(4):
                value = date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
            else:
                value = date(int(match.group(9)), RUSSIAN_MONTHS[match.group(8).lower()], int(match.group(7)))
        except (ValueError, KeyError):
            continue
        found.append((value, match.start()))
    return found


def _document_headings(text: str, doc_type: str) -> list[tuple[str, str]]:
    """Return number and nearby heading evidence, stopping before contract terms."""
    label = DOCUMENT_LABELS.get(doc_type)
    if not label:
        return []
    headings: list[tuple[str, str]] = []
    for heading in re.finditer(rf"\b{label}\b", text, re.I):
        line_end = text.find("\n", heading.start())
        if line_end == -1:
            line_end = len(text)
        heading_line = text[heading.start():line_end]
        contract = re.search(r"\bдоговор(?:у|а|ом)?\b", heading_line, re.I)
        number_match = re.search(r"(?:№|\bN\b|\bномер\b)\s*([\w/-]{1,40})", heading_line, re.I)
        if not number_match or (contract and contract.start() < number_match.start()):
            continue
        # Include one following line for dates printed below the document title.
        next_end = text.find("\n", line_end + 1)
        if next_end == -1:
            next_end = len(text)
        segment = text[heading.start():min(next_end, heading.start() + 220)]
        contract_in_segment = re.search(r"\bдоговор(?:у|а|ом)?\b", segment, re.I)
        if contract_in_segment:
            segment = segment[:contract_in_segment.start()]
        headings.append((number_match.group(1), segment))
    return headings


def _candidate_number(text: str, doc_type: str) -> str | None:
    numbers = {number for number, _ in _document_headings(text, doc_type)}
    return next(iter(numbers)) if len(numbers) == 1 else None


def _candidate_date(text: str, doc_type: str) -> str | None:
    values = {
        value for _, heading in _document_headings(text, doc_type)
        for value, _ in _dates_in_text(heading)
    }
    return next(iter(values)).isoformat() if len(values) == 1 else None


def _manual_heading_evidence(excerpt: str, doc_type: str, number: str, issued_on: date) -> bool:
    label = DOCUMENT_LABELS.get(doc_type)
    if not label:
        return False
    heading = re.search(rf"\b{label}\b", excerpt, re.I)
    if not heading:
        return False
    tail = excerpt[heading.end():]
    marker = re.search(rf"(?:№|\bN\b|\bномер\b)\s*{re.escape(number)}(?![\w/-])", tail, re.I)
    marked_number = marker is not None
    if marker is None:
        marker = re.search(rf"(?<![\w/-]){re.escape(number)}(?![\w/-])", tail)
    if marker is None or marker.start() > 80:
        return False
    contract = re.search(r"\bдоговор(?:у|а|ом)?\b", tail, re.I)
    dates = [position for value, position in _dates_in_text(excerpt) if value == issued_on]
    if not marked_number and dates and heading.end() + marker.start() > min(dates):
        return False
    return bool(dates and any(
        position >= heading.start() and (contract is None or position < heading.end() + contract.start())
        for position in dates
    )) and (contract is None or marker.start() < contract.start())


def _candidate_amount(text: str) -> float | None:
    matches = list(re.finditer(
        r"(?:итого|всего(?:\s+к\s+оплате)?)\s*[:—-]?\s*([\d\s\u00a0]+,\d{2})\b",
        text, re.I,
    ))
    if len(matches) != 1:
        return None
    try:
        return round(float(matches[0].group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")), 2)
    except ValueError:
        return None


async def review_legacy_document(
    session: AsyncSession, customer_id: int, document_id: int, scope: TenantScope,
) -> dict | None:
    doc = await _load_document(session, customer_id, document_id, scope)
    if doc is None:
        return None
    if doc.status is not None or not doc.google_file_id:
        raise LegacyDocumentReviewError("Проверка доступна только для старого Google-документа")
    try:
        source_text = await asyncio.to_thread(_text_from_google, doc.google_file_id)
    except LegacyDocumentReviewError:
        raise
    except Exception as exc:
        raise LegacyDocumentReviewError("Не удалось прочитать оригинал Google-документа") from exc
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    contract_id = doc.base_customer_contract_id
    if contract_id is None:
        numbers = set(re.findall(r"договор(?:у|а|ом)?\s*№\s*([\w/-]{1,40})", source_text, re.I))
        if len(numbers) == 1:
            contracts = (await session.execute(
                select(CustomerContract).where(
                    CustomerContract.customer_id == customer_id,
                    CustomerContract.number == next(iter(numbers)),
                )
            )).scalars().all()
            if len(contracts) == 1:
                contract_id = contracts[0].id
    return {
        "document_id": doc.id,
        "source_file_id": doc.google_file_id,
        "source_hash": source_hash,
        "extracted_text": source_text,
        "proposed_number": _candidate_number(source_text, doc.doc_type),
        "proposed_date": _candidate_date(source_text, doc.doc_type),
        "proposed_amount": _candidate_amount(source_text),
        "proposed_contract_id": contract_id,
        "_doc_type": doc.doc_type,
    }


async def confirm_legacy_document(
    session: AsyncSession, customer_id: int, document_id: int, scope: TenantScope,
    payload: ManagerLegacyReconciliationConfirmPayload,
    *, confirmed_by: str,
) -> dict | None:
    if scope.demo_read_only:
        raise LegacyDocumentReviewError("Демо-данные доступны только для просмотра")
    review = await review_legacy_document(session, customer_id, document_id, scope)
    if review is None:
        return None
    if review["source_hash"] != payload.source_hash:
        raise LegacyDocumentReviewError("Оригинал изменился: откройте проверку повторно")
    excerpt = " ".join(payload.evidence_excerpt.split())
    source = " ".join(review["extracted_text"].split())
    if excerpt not in source:
        raise LegacyDocumentReviewError("Фрагмент подтверждения не найден в оригинале")
    doc_type = review["_doc_type"]
    headings = _document_headings(source, doc_type)
    matching_headings = [heading for number, heading in headings if number == payload.number.strip()]
    if headings and not matching_headings:
        raise LegacyDocumentReviewError("Подтверждённый номер не найден в оригинале")
    if not _manual_heading_evidence(excerpt, doc_type, payload.number.strip(), payload.date):
        raise LegacyDocumentReviewError("Фрагмент должен содержать номер и дату самого документа")
    heading_dates = {
        value for heading in matching_headings for value, _ in _dates_in_text(heading)
    }
    if heading_dates and payload.date not in heading_dates:
        raise LegacyDocumentReviewError("Подтверждённая дата не найдена в оригинале")
    expected_amount = f"{payload.amount:.2f}".replace(".", ",")
    compact_source = source.replace("\u00a0", "").replace(" ", "")
    if expected_amount not in compact_source and f"{payload.amount:.2f}" not in compact_source:
        raise LegacyDocumentReviewError("Подтверждённая сумма не найдена в оригинале")
    if payload.contract_id is not None:
        contract = await session.get(CustomerContract, payload.contract_id)
        if contract is None or contract.customer_id != customer_id:
            raise LegacyDocumentReviewError("Договор не принадлежит этому контрагенту")
        if not re.search(rf"№\s*{re.escape(contract.number)}(?![\w/-])", source, re.I):
            raise LegacyDocumentReviewError("Номер договора не найден в оригинале")
    doc = await _load_document(session, customer_id, document_id, scope, lock=True)
    if doc is None or doc.status is not None or doc.google_file_id != review["source_file_id"]:
        raise LegacyDocumentReviewError("Документ изменился: откройте проверку повторно")
    meta = dict(doc.scope_meta or {})
    meta[LEGACY_META_KEY] = {
        "source_file_id": doc.google_file_id,
        "source_hash": review["source_hash"],
        "number": payload.number.strip(),
        "date": payload.date.isoformat(),
        "amount": round(payload.amount, 2),
        "contract_id": payload.contract_id,
        "evidence_excerpt": excerpt,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_by": confirmed_by,
    }
    doc.scope_meta = meta
    session.add(doc)
    await session.commit()
    return {
        "document_id": doc.id,
        "number": meta[LEGACY_META_KEY]["number"],
        "date": payload.date,
        "amount": meta[LEGACY_META_KEY]["amount"],
        "contract_id": payload.contract_id,
        "source_hash": review["source_hash"],
    }
