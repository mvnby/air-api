"""Conservative ledger projection from issued delivery evidence and allocations."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from models import Order, OrderDocument, Payment
from services.customer_reconciliation_legacy_review import LEGACY_META_KEY
from services.documents.base import DOC_NAMES
from services.order_financial_eligibility import is_successful_order


DELIVERY_DOC_TYPES = frozenset({
    "act", "tn2", "ttn1", "retail_receipt", "service_act", "maintenance_service_act",
})
ACTIVE_STATUSES = frozenset({None, "issued", "sent", "signed"})
EVENT_RELATIONS_META_KEY = "reconciliation_event_relations"


def money(value: Any) -> float:
    return round(float(value or 0), 2)


def _snapshot_amount(doc: OrderDocument) -> float | None:
    rows = ((doc.render_snapshot or {}).get("table_rows") or {}).get("lines")
    if not isinstance(rows, list) or not rows:
        return None
    total = Decimal("0")
    try:
        for row in rows:
            raw = str(row["line.amount"]).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            total += Decimal(raw)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    return money(total)


def _confirmed(doc: OrderDocument) -> dict[str, Any] | None:
    if doc.status is not None:
        return None
    data = (doc.scope_meta or {}).get(LEGACY_META_KEY)
    if not isinstance(data, dict) or data.get("source_file_id") != doc.google_file_id:
        return None
    try:
        datetime.fromisoformat(data["date"])
        float(data["amount"])
        if not str(data["number"]).strip() or not str(data["source_hash"]).strip():
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return data


def document_identity(doc: OrderDocument) -> dict[str, Any]:
    confirmed = _confirmed(doc)
    if doc.status is not None:
        value_date = doc.official_date
        official_number = f"{doc.official_series or ''}{doc.official_number or ''}".strip()
        source = "official" if value_date and official_number else "unverified_managed"
        number = official_number or doc.number
        amount = _snapshot_amount(doc)
        amount_source = "frozen_snapshot" if amount is not None else None
        contract_id = doc.base_customer_contract_id or ((doc.render_snapshot or {}).get("meta") or {}).get("base_customer_contract_id")
    elif confirmed:
        value_date = date.fromisoformat(confirmed["date"])
        number = confirmed["number"]
        source = "confirmed_legacy"
        amount = money(confirmed["amount"])
        amount_source = "confirmed_legacy"
        contract_id = confirmed.get("contract_id") or doc.base_customer_contract_id
    else:
        value_date = doc.date
        number = doc.number
        source = "unverified_legacy"
        amount = None
        amount_source = None
        contract_id = doc.base_customer_contract_id
    if isinstance(value_date, date) and not isinstance(value_date, datetime):
        value_date = datetime.combine(value_date, time.min)
    return {
        "id": doc.id, "doc_type": doc.doc_type,
        "doc_type_label": DOC_NAMES.get(doc.doc_type, doc.doc_type.upper()),
        "number": number, "date": value_date or doc.date,
        "edit_url": doc.google_edit_url,
        "identity_source": source,
        "amount_source": amount_source, "amount": amount,
        "contract_id": contract_id,
        "_line_key": tuple(
            sorted(str(row) for row in (((doc.render_snapshot or {}).get("table_rows") or {}).get("lines") or []))
        ),
    }


def event_fingerprint(doc: OrderDocument) -> str:
    """Fingerprint the evidence; prior confirmations expire after source edits."""
    meta = dict(doc.scope_meta or {})
    meta.pop(EVENT_RELATIONS_META_KEY, None)
    identity = document_identity(doc)
    evidence = {
        "document_id": doc.id, "order_id": doc.order_id,
        "status": doc.status, "doc_type": doc.doc_type,
        "number": identity["number"], "date": identity["date"],
        "amount": identity["amount"], "contract_id": identity["contract_id"],
        "identity_source": identity["identity_source"],
        "google_file_id": doc.google_file_id,
        "render_snapshot": doc.render_snapshot,
        "scope_meta": meta,
    }
    raw = json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def confirmed_event_relation(first: OrderDocument, second: OrderDocument) -> str | None:
    first_records = (first.scope_meta or {}).get(EVENT_RELATIONS_META_KEY) or {}
    second_records = (second.scope_meta or {}).get(EVENT_RELATIONS_META_KEY) or {}
    if not isinstance(first_records, dict) or not isinstance(second_records, dict):
        return None
    matching = []
    for key, record in first_records.items():
        if record != second_records.get(key) or not isinstance(record, dict):
            continue
        ids = record.get("document_ids") or []
        hashes = record.get("fingerprints") or {}
        if first.id not in ids or second.id not in ids:
            continue
        if (hashes.get(str(first.id)) != event_fingerprint(first)
                or hashes.get(str(second.id)) != event_fingerprint(second)):
            continue
        if record.get("relation") in {"same", "separate"}:
            matching.append(record)
    if not matching:
        return None
    return max(matching, key=lambda record: record.get("confirmed_at") or "")["relation"]


def _warning(code: str, message: str, *, order_id: int | None = None,
             document_id: int | None = None, payment_id: int | None = None,
             related_document_ids: list[int] | None = None,
             can_review_legacy: bool = False) -> dict:
    return {"code": code, "message": message, "order_id": order_id,
            "document_id": document_id, "payment_id": payment_id,
            "related_document_ids": related_document_ids or [],
            "can_review_legacy": can_review_legacy}


def _payment_contract(order: Order, docs: list[dict]) -> int | None:
    associated = {item["contract_id"] for item in docs if item["contract_id"] is not None}
    if len(associated) > 1:
        return None
    if associated:
        return next(iter(associated))
    return order.customer_contract_id


def _payment_date(payment: Payment) -> datetime:
    receipt = payment.bank_receipt
    return (receipt.received_at if receipt and receipt.received_at else payment.date)


def project(orders: list[Order], period_start: datetime, period_end: datetime,
            contract_id: int | None = None,
            receipt_allocated_totals: dict[int, float] | None = None) -> dict[str, Any]:
    warnings: list[dict] = []
    documents: list[dict] = []
    payments: list[dict] = []
    opening_documents = opening_payments = 0.0
    documents_total = payments_total = 0.0
    receipt_groups: dict[tuple[int, int | None, str], list[tuple[Order, Payment]]] = {}
    plain_payments: list[tuple[Order, Payment, int | None, float | None]] = []
    all_allocated_by_receipt: dict[int, float] = {}
    for order in orders:
        for payment in order.payments:
            if payment.bank_receipt_id and _payment_date(payment) <= period_end:
                receipt_id = int(payment.bank_receipt_id)
                all_allocated_by_receipt[receipt_id] = money(
                    all_allocated_by_receipt.get(receipt_id, 0) + payment.amount
                )
    if receipt_allocated_totals is not None:
        all_allocated_by_receipt = receipt_allocated_totals

    for order in orders:
        superseded_ids = {
            doc.replaces_document_id for doc in order.documents
            if doc.replaces_document_id is not None
            and doc.status in {"issued", "sent", "signed"}
        }
        active_docs = [doc for doc in order.documents
                       if doc.doc_type in DELIVERY_DOC_TYPES and doc.status in ACTIVE_STATUSES
                       and doc.id not in superseded_ids]
        all_delivery_docs = [doc for doc in order.documents if doc.doc_type in DELIVERY_DOC_TYPES]
        identities = [document_identity(doc) for doc in active_docs]
        docs_by_id = {doc.id: doc for doc in active_docs}
        stale_relation_keys: set[str] = set()
        for doc in active_docs:
            if document_identity(doc)["date"] > period_end:
                continue
            records = (doc.scope_meta or {}).get(EVENT_RELATIONS_META_KEY) or {}
            if not isinstance(records, dict):
                continue
            for key, record in records.items():
                if key in stale_relation_keys or not isinstance(record, dict):
                    continue
                if (record.get("fingerprints") or {}).get(str(doc.id)) != event_fingerprint(doc):
                    stale_relation_keys.add(key)
                    warnings.append(_warning(
                        "event_relation_stale",
                        "Подтверждение связи документов устарело после изменения источника",
                        order_id=order.id, document_id=doc.id,
                        related_document_ids=record.get("document_ids") or [],
                    ))
        payment_contract = _payment_contract(order, identities)
        if contract_id is not None and order.payments and payment_contract is None:
            warnings.append(_warning("payment_contract_unknown", "Привязка платежа к договору не подтверждена", order_id=order.id))

        if active_docs or is_successful_order(order):
            included = [item for item in identities if contract_id is None or item["contract_id"] == contract_id]
            if contract_id is not None and any(item["contract_id"] is None and item["date"] <= period_end for item in identities):
                warnings.append(_warning("document_contract_unknown", "Привязка закрывающего документа к договору не подтверждена", order_id=order.id))
            included = [item for item in included if item["date"] <= period_end]
            known = [item for item in included if item["amount"] is not None]
            unknown = [item for item in included if item["amount"] is None]
            for item in unknown:
                warnings.append(_warning("document_source_unverified", "Нужно проверить оригинал и сумму закрывающего документа", order_id=order.id, document_id=item["id"], can_review_legacy=item["identity_source"] == "unverified_legacy"))
            for item in known:
                if item["identity_source"] not in {"official", "confirmed_legacy"}:
                    warnings.append(_warning("document_identity_unverified", "У закрывающего документа нет подтверждённых номера и даты", order_id=order.id, document_id=item["id"]))
            # Distinct document types with the same frozen/confirmed event are print variants.
            events: list[list[dict]] = []
            for item in sorted(known, key=lambda row: (row["date"], row["id"])):
                match = None
                ambiguous = False
                for event in events:
                    first = event[0]
                    if (first["date"].date() != item["date"].date()
                            or first["amount"] != item["amount"]
                            or first["contract_id"] != item["contract_id"]):
                        continue
                    relations = [confirmed_event_relation(docs_by_id[part["id"]], docs_by_id[item["id"]])
                                 for part in event]
                    if "separate" in relations:
                        continue
                    if all(relation == "same" for relation in relations):
                        match = event
                        break
                    if item["doc_type"] not in {part["doc_type"] for part in event}:
                        match = event
                        ambiguous = True
                        break
                if match is None:
                    events.append([item])
                else:
                    if ambiguous:
                        warnings.append(_warning(
                            "possible_duplicate_delivery_event",
                            "Документы могут отражать одно или разные события: сумма предварительная",
                            order_id=order.id, document_id=item["id"],
                            related_document_ids=[part["id"] for part in match] + [item["id"]],
                        ))
                    match.append(item)
            fallback_date = order.closed_at or order.contract_date or order.created_at
            if (is_successful_order(order) and not events and not unknown and contract_id is None and not all_delivery_docs
                    and money(order.total_amount) > 0 and fallback_date <= period_end):
                warnings.append(_warning("order_total_without_source", "Сумма заказа не подтверждена закрывающим документом", order_id=order.id))
                events = [[{"date": fallback_date, "amount": money(order.total_amount), "number": str(order.id),
                            "doc_type_label": "Заказ", "contract_id": order.customer_contract_id,
                            "_fallback": True}]]
            elif (not events and all_delivery_docs and not active_docs
                  and any(doc.date <= period_end for doc in all_delivery_docs)):
                warnings.append(_warning("delivery_document_inactive", "Закрывающий документ отменён, заменён или не выпущен", order_id=order.id))
            elif (is_successful_order(order) and not events and not unknown and contract_id is not None and not all_delivery_docs
                  and money(order.total_amount) > 0 and fallback_date <= period_end
                  and order.customer_contract_id in {None, contract_id}):
                warnings.append(_warning("document_source_missing", "Сумма по договору не подтверждена закрывающим документом", order_id=order.id))
            for event in events:
                first = event[0]
                amount = first["amount"]
                when = first["date"]
                if when > period_end:
                    continue
                basis = ", ".join(f"{item['doc_type_label']} №{item['number']}" for item in event)
                row = {"order_id": order.id, "order_title": order.title or f"Заказ #{order.id}",
                       "date": when, "amount": amount, "basis": basis,
                       "delivery_address": order.delivery_address,
                       "documents": [{key: value for key, value in item.items() if not key.startswith("_")}
                                     for item in event if not item.get("_fallback")],
                       "contract_id": first["contract_id"],
                       "amount_source": "order_total_unverified" if first.get("_fallback") else first["amount_source"]}
                if when < period_start:
                    opening_documents += amount
                else:
                    documents_total += amount
                    documents.append(row)
            if unknown and not known and contract_id is None and money(order.total_amount) > 0:
                fallback_date = min(item["date"] for item in unknown)
                amount = money(order.total_amount)
                warnings.append(_warning("order_total_unverified", "Показана сумма заказа вместо неподтверждённой суммы документов", order_id=order.id))
                row = {"order_id": order.id, "order_title": order.title or f"Заказ #{order.id}",
                       "date": fallback_date, "amount": amount,
                       "basis": ", ".join(f"{item['doc_type_label']} · внутр. №{item['number']}" for item in unknown),
                       "delivery_address": order.delivery_address,
                       "documents": [{key: value for key, value in item.items() if not key.startswith("_")} for item in unknown],
                       "contract_id": payment_contract, "amount_source": "order_total_unverified"}
                if fallback_date < period_start:
                    opening_documents += amount
                elif fallback_date <= period_end:
                    documents_total += amount
                    documents.append(row)

        # Advances on open orders are real receipts even before delivery.
        if str(getattr(order.closing_result, "value", order.closing_result)) == "lost":
            if any(money(payment.amount) > 0 and _payment_date(payment) <= period_end for payment in order.payments):
                warnings.append(_warning("payment_on_lost_order", "Платёж по отказному заказу требует проверки возврата или назначения", order_id=order.id))
            continue
        for payment in order.payments:
            payment_date = _payment_date(payment)
            if payment_date > period_end:
                continue
            if money(payment.amount) <= 0:
                continue
            if str(getattr(payment.currency, "value", payment.currency)) != "BYN":
                warnings.append(_warning("payment_currency_unknown", "Для валютного платежа нет курса пересчёта в BYN", order_id=order.id, payment_id=payment.id))
                continue
            if contract_id is not None and payment_contract != contract_id:
                continue
            if payment.bank_receipt_id:
                period_bucket = "opening" if payment_date < period_start else "current"
                receipt_groups.setdefault((int(payment.bank_receipt_id), payment_contract, period_bucket), []).append((order, payment))
            else:
                plain_payments.append((order, payment, payment_contract, None))

    for (_, group_contract, _), group in receipt_groups.items():
        order, representative = min(group, key=lambda pair: _payment_date(pair[1]))
        receipt = representative.bank_receipt
        amount = money(sum(payment.amount for _, payment in group))
        if receipt is not None and receipt.received_at is None and len({payment.date for _, payment in group}) > 1:
            warnings.append(_warning("receipt_date_unverified", "У распределений одного банковского поступления разные даты", payment_id=representative.id))
        if (receipt is not None
                and all_allocated_by_receipt.get(receipt.id, 0.0) > money(receipt.amount)):
            warnings.append(_warning("receipt_overallocated", "Распределения превышают сумму банковского поступления", payment_id=representative.id))
        if (receipt is not None
                and all_allocated_by_receipt.get(receipt.id, 0.0) < money(receipt.amount)):
            warnings.append(_warning("receipt_partially_allocated", "Часть банковского поступления не распределена на эту сверку", payment_id=representative.id))
        plain_payments.append((order, representative, group_contract, amount))
    for order, payment, payment_contract, amount_override in plain_payments:
        amount = money(payment.amount if amount_override is None else amount_override)
        payment_date = _payment_date(payment)
        if payment_date > period_end:
            continue
        receipt = payment.bank_receipt
        row = {"payment_id": payment.id, "order_id": order.id,
               "order_title": order.title or f"Заказ #{order.id}", "date": payment_date,
               "amount": amount, "allocated_amount": amount,
               "currency": payment.currency, "payment_type": payment.type,
               "comment": payment.comment, "bank_receipt_id": receipt.id if receipt else None,
               "payer_name": receipt.payer_name if receipt else None,
               "payer_unp": receipt.payer_unp if receipt else None,
               "payer_account": receipt.payer_account if receipt else None,
               "our_account": receipt.our_account if receipt else None,
               "payment_document_number": receipt.payment_document_number if receipt else None,
               "payment_document_raw": receipt.payment_document_raw if receipt else None,
               "payment_purpose": receipt.payment_purpose if receipt else None,
               "contract_id": payment_contract}
        if payment_date < period_start:
            opening_payments += amount
        else:
            payments_total += amount
            payments.append(row)
    return {
        "opening_balance": money(opening_documents - opening_payments),
        "documents_total": money(documents_total), "payments_total": money(payments_total),
        "closing_balance": money(opening_documents - opening_payments + documents_total - payments_total),
        "documents": sorted(documents, key=lambda row: (row["date"], row["order_id"])),
        "payments": sorted(payments, key=lambda row: (row["date"], row["payment_id"])),
        "warnings": warnings, "ready_for_generation": not warnings,
    }
