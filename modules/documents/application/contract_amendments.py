"""Frozen contract basis and effective amendment calculation shared by Manager/MCP."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from sqlmodel import select
from models import DocumentLegalEntity, Order, OrderDocument, OrderStatus
from modules.documents.domain.contract_amendment import (
    TYPE,
    BASIS_TYPES,
    ACTIVE_STATUSES,
    ContractAmendmentTerms,
)
from .commercial_rows import line_row
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .value_formatters import money, amount_in_words


def revision(basis, active):
    return sha256(
        json.dumps(
            {
                "basis": [basis.id, basis.status, basis.render_snapshot],
                "active": [[d.id, d.status, d.render_snapshot] for d in active],
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


async def load_basis(
    session, *, scope, order_id, basis_id, lock=False, require_active=True
):
    query = (
        select(OrderDocument)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            OrderDocument.id == basis_id,
            OrderDocument.order_id == order_id,
            OrderDocument.tenant_id == scope.tenant_id,
            Order.tenant_id == scope.tenant_id,
            Order.storefront_id == scope.storefront_id,
            OrderDocument.doc_type.in_(BASIS_TYPES),
        )
    )
    if require_active:
        query = query.where(OrderDocument.status.in_(ACTIVE_STATUSES))
    if lock:
        query = query.with_for_update(of=OrderDocument).execution_options(
            populate_existing=True
        )
    basis = await session.scalar(query)
    if basis is None:
        raise ManagedDocumentNotFoundError(
            "Выберите действующий выпущенный договор этого заказа"
        )
    values = (basis.render_snapshot or {}).get("values", {})
    try:
        amount = Decimal(values["totals.amount"])
        if (
            not amount.is_finite()
            or amount < 0
            or values.get("totals.currency") != "BYN"
        ):
            raise ValueError()
    except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
        raise ManagedDocumentConflictError(
            "У договора нет зафиксированной суммы в BYN. Требуется сверка основания"
        ) from exc
    return basis


async def active_amendments(session, basis, *, excluding_id=None):
    query = (
        select(OrderDocument)
        .where(
            OrderDocument.tenant_id == basis.tenant_id,
            OrderDocument.order_id == basis.order_id,
            OrderDocument.base_document_id == basis.id,
            OrderDocument.doc_type == TYPE,
            OrderDocument.status.in_(ACTIVE_STATUSES),
        )
        .order_by(OrderDocument.id)
    )
    if excluding_id is not None:
        query = query.where(OrderDocument.id != excluding_id)
    return list(
        (await session.scalars(query.execution_options(populate_existing=True))).all()
    )


async def calculation(session, basis, *, replacing_id=None):
    active = await active_amendments(session, basis)
    original = Decimal(basis.render_snapshot["values"]["totals.amount"])
    other = sum(
        (
            Decimal(d.render_snapshot["values"]["totals.amount"])
            for d in active
            if d.id != replacing_id
        ),
        Decimal("0"),
    )
    return original, other, revision(basis, active)


async def list_bases(session, *, scope, order_id, limit=100):
    from .lifecycle_service import ManagedDocumentService

    documents = await ManagedDocumentService.list_for_order(
        session, tenant_scope=scope, order_id=order_id
    )
    result = []
    for basis in documents:
        if (
            basis.doc_type not in BASIS_TYPES
            or basis.status not in ACTIVE_STATUSES
            or basis.tenant_id != scope.tenant_id
        ):
            continue
        try:
            await load_basis(session, scope=scope, order_id=order_id, basis_id=basis.id)
        except ManagedDocumentConflictError:
            continue
        original, additions, version = await calculation(session, basis)
        values = basis.render_snapshot["values"]
        result.append(
            dict(
                document_id=basis.id,
                legal_entity_id=basis.legal_entity_id,
                number=values.get("document.official_full_number") or basis.number,
                date=values.get("document.issued_on") or None,
                status=basis.status,
                original_amount=money(original),
                effective_additions=money(additions),
                agreed_total=money(original + additions),
                currency="BYN",
                revision=version,
                seller_name=values.get("seller.legal_name", ""),
                customer_name=values.get("customer.full_name", ""),
                lines=basis.render_snapshot.get("table_rows", {}).get("lines", []),
            )
        )
    return result[: min(limit, 100)]


def apply_terms(snapshot, terms):
    terms = ContractAmendmentTerms.model_validate(terms)
    amendment = snapshot["meta"]["amendment"]
    original = Decimal(amendment["original_amount"])
    other = Decimal(amendment["other_amendments_amount"])
    rows = []
    for i, work in enumerate(terms.works, 1):
        row = line_row(
            i,
            title=work.title,
            kind="service",
            quantity=work.quantity,
            unit=work.unit,
            unit_price=work.unit_price,
        )
        row["line.vat_label"] = snapshot["values"].get("totals.vat_label", "")
        rows.append({k: v for k, v in row.items() if not k.endswith("_raw")})
    snapshot["table_rows"] = {"lines": rows}
    snapshot["meta"].setdefault("draft_parameters", {})["amendment_terms"] = (
        terms.model_dump(mode="json")
    )
    snapshot["values"].update(
        {
            "totals.amount": money(terms.amount),
            "totals.amount_in_words": amount_in_words(terms.amount),
            "amendment.original_amount": money(original),
            "amendment.other_amount": money(other),
            "amendment.previous_total": money(original + other),
            "amendment.new_total": money(original + other + terms.amount),
            **{
                f"amendment.{key}": getattr(terms, key)
                for key in (
                    "equipment",
                    "acceptance_terms",
                    "payment_terms",
                    "effective_terms",
                )
            },
        }
    )


async def build_snapshot(session, *, scope, selection, replacing=None):
    if replacing is not None:
        if selection.base_document_id not in (None, replacing.base_document_id):
            raise ManagedDocumentConflictError(
                "Новая редакция сохраняет исходный договор этого соглашения"
            )
        basis_id = replacing.base_document_id
    else:
        basis_id = selection.base_document_id
    if not basis_id or selection.base_customer_contract_id:
        raise ManagedDocumentConflictError(
            "Явно выберите конкретный выпущенный договор заказа"
        )
    basis = await load_basis(
        session, scope=scope, order_id=selection.order_id, basis_id=basis_id
    )
    if basis.legal_entity_id != selection.legal_entity_id or not await session.scalar(
        select(DocumentLegalEntity.id).where(
            DocumentLegalEntity.id == selection.legal_entity_id,
            DocumentLegalEntity.tenant_id == scope.tenant_id,
            DocumentLegalEntity.status == "active",
        )
    ):
        raise ManagedDocumentConflictError(
            "Выберите юридическое лицо исходного договора"
        )
    original, other, version = await calculation(
        session, basis, replacing_id=replacing.id if replacing else None
    )
    if replacing is None and selection.amendment_basis_revision != version:
        raise ManagedDocumentConflictError(
            "Основание или действующие соглашения изменились. Перечитайте договор и расчёт"
        )
    if replacing:
        snapshot = deepcopy(replacing.render_snapshot)
        terms = (
            selection.amendment_terms
            or snapshot["meta"]["draft_parameters"]["amendment_terms"]
        )
    else:
        if selection.amendment_terms is None:
            raise ManagedDocumentConflictError("Добавьте дополнительные работы")
        terms = selection.amendment_terms
        if not terms.equipment:
            frozen = basis.render_snapshot["values"]
            equipment = " ".join(
                str(frozen.get(f"equipment.{key}") or "").strip()
                for key in ("brand", "model", "serial")
            ).strip()
            if not equipment:
                equipment = "; ".join(
                    row.get("line.title", "")
                    for row in basis.render_snapshot.get("table_rows", {}).get(
                        "lines", []
                    )
                    if row.get("line.kind") == "product"
                )
            terms = terms.model_copy(update={"equipment": equipment[:2000]})
        values = {
            k: v
            for k, v in basis.render_snapshot["values"].items()
            if k.startswith(
                (
                    "seller.",
                    "customer.",
                    "order.",
                    "totals.currency",
                    "totals.vat_label",
                )
            )
        }
        snapshot = dict(
            schema_version=5,
            meta={},
            values=values,
            conditions={
                k: v
                for k, v in basis.render_snapshot.get("conditions", {}).items()
                if k.startswith(("seller.", "customer.", "order."))
            },
        )
    values = snapshot["values"]
    for key in (
        "internal_reference",
        "official_series",
        "official_number",
        "official_full_number",
    ):
        values[f"document.{key}"] = ""
    values.update(
        {
            "document.type": TYPE,
            "document.issued_on": selection.issue_date.strftime("%d.%m.%Y"),
            "document.issue_city": selection.issue_city
            or values.get("document.issue_city")
            or basis.render_snapshot["values"].get("document.issue_city", ""),
            "basis.type": "Договор",
            "basis.number": basis.render_snapshot["values"].get(
                "document.official_full_number", ""
            ),
            "basis.date": basis.render_snapshot["values"].get("document.issued_on", ""),
        }
    )
    snapshot["meta"].update(
        tenant_id=scope.tenant_id,
        order_id=selection.order_id,
        legal_entity_id=selection.legal_entity_id,
        document_type=TYPE,
        proposal_id=None,
        base_document_id=basis.id,
        base_customer_contract_id=None,
        amendment={
            "basis_revision": version,
            "original_amount": money(original),
            "other_amendments_amount": money(other),
        },
    )
    apply_terms(snapshot, terms)
    return snapshot


async def validate_for_issue(session, *, scope, document):
    if document.doc_type != TYPE:
        return
    if (
        await session.scalar(select(Order.status).where(Order.id == document.order_id))
        == OrderStatus.CLOSED
    ):
        raise ManagedDocumentConflictError(
            "Заказ завершён: выпуск допсоглашения недоступен"
        )
    basis = await load_basis(
        session,
        scope=scope,
        order_id=document.order_id,
        basis_id=document.base_document_id,
        lock=True,
    )
    _, _, version = await calculation(
        session, basis, replacing_id=document.replaces_document_id
    )
    if version != document.render_snapshot["meta"]["amendment"]["basis_revision"]:
        raise ManagedDocumentConflictError(
            "Действующие соглашения или договор изменились. Создайте новый черновик с актуальным итогом"
        )
    values = document.render_snapshot["values"]
    missing = [key for key in ("basis.number", "basis.date") if not values.get(key)]
    if missing:
        raise ManagedDocumentConflictError(
            "Заполните реквизиты исходного договора: " + ", ".join(missing)
        )
