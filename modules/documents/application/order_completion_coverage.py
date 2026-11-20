"""Protect commercial quantities and value across act issue reservations."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Mapping

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink
from modules.documents.domain.lifecycle import DocumentStatus
from services.order_proposal_version import proposal_version

from .errors import ManagedDocumentConflictError


if TYPE_CHECKING:
    from schemas_order_sites import OrderSiteItem

COVERAGE_KEY = "completion_act_coverage"
LineKey = tuple[str, int]


@dataclass(frozen=True, slots=True)
class CompletionActScope:
    sites: tuple["OrderSiteItem", ...]
    proposal_version: str

    @property
    def site_ids(self) -> list[int]:
        return [item.id for item in self.sites]

    @property
    def title(self) -> str:
        return self.sites[0].title if len(self.sites) == 1 else "Объекты работ"

    @property
    def printable_address(self) -> str:
        if len(self.sites) == 1:
            return self.sites[0].address
        return "\n".join(f"{item.title} — {item.address}" for item in self.sites)


@dataclass(frozen=True, slots=True)
class LineUse:
    quantity: int = 0
    amount: Decimal = Decimal(0)

    def __add__(self, other):
        return LineUse(self.quantity + other.quantity, self.amount + other.amount)

    def held_with(self, other):
        return LineUse(max(self.quantity, other.quantity), max(self.amount, other.amount))


def require_scope_in_template(placeholder_schema: Mapping[str, object] | None) -> None:
    if "order.object_address" not in (placeholder_schema or {}).get("fields", []):
        raise ManagedDocumentConflictError(
            "В шаблоне акта нет поля «Адрес объекта». Добавьте {{ order.object_address }}, чтобы вывести все объекты."
        )


def selected_coverage(
    scope: CompletionActScope, products, services, product_quantities: Mapping[int, int],
) -> dict:
    lines = [
        ("product", item, product_quantities.get(item.id, item.quantity))
        for item in products
    ] + [("service", item, quantity) for item, quantity in services]
    if not lines:
        raise ValueError("Выберите работы или материалы из предложения")
    resolved = []
    for kind, item, quantity in lines:
        unit_price = Decimal(str(item.price or 0))
        if item.id is None or not 0 < quantity <= item.quantity or unit_price < 0:
            raise ValueError("Некорректное количество или стоимость строки предложения")
        resolved.append({"kind": kind, "line_id": item.id, "quantity": quantity, "unit_price": str(unit_price)})
    return {
        "schema_version": 1,
        "proposal_version": scope.proposal_version,
        "sites": [
            item.model_dump(mode="json", include={"id", "customer_branch_id", "title", "address", "version"})
            for item in scope.sites
        ],
        "lines": resolved,
    }


def _entry(document: OrderDocument) -> dict | None:
    return ((document.render_snapshot or {}).get("meta") or {}).get(COVERAGE_KEY)


def _basis(document: OrderDocument) -> tuple[int | None, int | None]:
    return document.base_document_id, document.base_customer_contract_id


def _usage(document: OrderDocument) -> dict[LineKey, LineUse]:
    coverage = _entry(document)
    if not coverage:
        raise ManagedDocumentConflictError(
            f"У ранее оформленного акта № {document.number} нет проверяемой разбивки по строкам. "
            "Уточните закрытые объёмы или оформите его исправление."
        )
    return {
        (line["kind"], line["line_id"]): LineUse(line["quantity"], Decimal(line["unit_price"]) * line["quantity"])
        for line in coverage["lines"]
    }


def combined_usage(documents: list[OrderDocument]) -> dict[LineKey, LineUse]:
    """Treat a numbered replacement and its still-active source as one hold."""
    by_id = {row.id: _usage(row) for row in documents}
    for row in documents:
        source = by_id.get(row.replaces_document_id)
        if source is not None and row.status == DocumentStatus.DRAFT.value:
            replacement = by_id.pop(row.id)
            for key in source.keys() | replacement.keys():
                source[key] = source.get(key, LineUse()).held_with(replacement.get(key, LineUse()))
    total: dict[LineKey, LineUse] = defaultdict(LineUse)
    for partial in by_id.values():
        for key, used in partial.items():
            total[key] += used
    return dict(total)


async def _effective_acts(session: AsyncSession, order_id: int) -> list[OrderDocument]:
    statement = select(OrderDocument).where(
        OrderDocument.order_id == order_id,
        OrderDocument.doc_type == "act",
        # A received file can support a native act without closing any volume.
        or_(OrderDocument.origin.is_(None), OrderDocument.external_status == "signed"),
        or_(
            OrderDocument.status.in_((DocumentStatus.ISSUED.value, DocumentStatus.SENT.value, DocumentStatus.SIGNED.value)),
            OrderDocument.status.is_(None),
            and_(OrderDocument.status == DocumentStatus.DRAFT.value, OrderDocument.official_number.is_not(None)),
        ),
    ).order_by(OrderDocument.id)
    return list((await session.scalars(statement.execution_options(populate_existing=True))).all())


async def ensure_legacy_act_write_allowed(session: AsyncSession, order_id: int) -> None:
    """Serialize unscoped act generation with other closing writes."""
    await session.scalar(select(Order.id).where(Order.id == order_id).with_for_update())
    effective = await _effective_acts(session, order_id)
    if any(row.external_status == "signed" for row in effective):
        raise ManagedDocumentConflictError(
            "В заказе уже есть подписанный внешний акт без проверяемой разбивки по строкам. "
            "Сначала сверьте ранее закрытые объёмы."
        )
    if any(_entry(row) for row in effective):
        raise ManagedDocumentConflictError(
            "По заказу уже оформлен акт по выбранным объектам. "
            "Подготовьте очередной акт из того же предложения с проверкой закрытых объёмов."
        )


async def ensure_signed_external_act_write_allowed(session: AsyncSession, order_id: int) -> None:
    """A signed import has no verifiable breakdown and cannot close alongside another act."""
    if await _effective_acts(session, order_id):
        raise ManagedDocumentConflictError(
            "По заказу уже оформлен акт. Приложите подписанную копию к существующему акту "
            "или импортируйте файл со статусом «Получен»."
        )


async def _limits(session: AsyncSession, order_id: int, proposal_id: int) -> dict[LineKey, LineUse]:
    result = {}
    for kind, model in (("service", OrderServiceLink), ("product", OrderProductLink)):
        rows = await session.scalars(
            select(model).where(model.order_id == order_id, model.proposal_id == proposal_id)
            .execution_options(populate_existing=True)
        )
        result.update({
            (kind, row.id): LineUse(row.quantity, Decimal(str(row.price or 0)) * row.quantity)
            for row in rows
        })
    return result


def verify_capacity(current: dict[LineKey, LineUse], prior: dict[LineKey, LineUse], limits: dict[LineKey, LineUse]):
    for key in current.keys() | prior.keys():
        limit = limits.get(key, LineUse())
        used = current.get(key, LineUse()) + prior.get(key, LineUse())
        if used.quantity > limit.quantity or used.amount > limit.amount:
            raise ManagedDocumentConflictError(
                "Акт превышает количество или сумму согласованной строки. Проверьте уже оформленные акты."
            )


async def validate_scoped_act_capacity(session: AsyncSession, document: OrderDocument) -> None:
    """Check under the order row lock, before persisting a draft or reserving its number."""
    coverage = _entry(document)
    if coverage is None:
        raise ValueError("У акта отсутствует разбивка по предложениям")
    proposal = await session.scalar(select(OrderProposal).where(
        OrderProposal.id == document.proposal_id, OrderProposal.order_id == document.order_id,
    ).execution_options(populate_existing=True))
    if (
        proposal is None or proposal.is_archived or not proposal.is_selected or proposal.status == "rejected"
        or coverage["proposal_version"] != await proposal_version(session, document.order_id, proposal.id)
    ):
        raise ManagedDocumentConflictError(
            "Предложение изменилось. Прочитайте его актуальную версию и заново подготовьте черновик."
        )
    prior = []
    for existing in await _effective_acts(session, document.order_id):
        if existing.id == document.id:
            continue
        if existing.id == document.replaces_document_id:
            if _basis(existing) != _basis(document) or existing.proposal_id not in {None, proposal.id}:
                raise ManagedDocumentConflictError("Исправление должно сохранить договор и предложение исходного акта")
            continue
        if existing.proposal_id != proposal.id or _basis(existing) != _basis(document):
            raise ManagedDocumentConflictError(
                "В заказе уже есть акт с другим основанием или предложением. Сначала сверьте ранее оформленные акты."
            )
        prior.append(existing)
    verify_capacity(_usage(document), combined_usage(prior), await _limits(session, document.order_id, proposal.id))


async def validate_act_before_number_reservation(session: AsyncSession, document: OrderDocument) -> None:
    if document.doc_type != "act" or document.official_number is not None:
        return
    if _entry(document):
        await validate_scoped_act_capacity(session, document)
    else:
        await ensure_legacy_act_write_allowed(session, document.order_id)
