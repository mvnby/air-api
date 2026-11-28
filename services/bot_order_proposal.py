"""Read and edit sales proposals within the order desk's command transaction."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.bot_order_proposal import (
    BotOrderAddEquipment, BotOrderAddInstallation, BotOrderInstallationOption,
    BotOrderRemoveLine, BotOrderSelectProposal, BotOrderUpdateLine, BotProposalChange,
)
from core.command_actor import CommandActor
from models import InstallationEstimateRevision, Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink
from models.tenancy import TenantScope
from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES
from schemas import ManagerTariffServiceKind
from schemas_installation_price_book import InstallationPreviewPayload
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.document_service import DocumentService
from services.inbox_eligibility import require_unarchived_inbox
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService
from services.installation_standard_catalogue_service import list_standard_tariffs
from services.maintenance_commercial_guard import guard_lines
from services.order_product_line_service import OrderProductLineService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_proposal_lifecycle import (
    PROPOSAL_STATUS_APPROVED, PROPOSAL_STATUS_DRAFT, PROPOSAL_STATUS_READY, PROPOSAL_STATUS_SENT,
)
from services.order_service import OrderService
from services.service_estimate_money import money, writable_service_money
from services.tariffs_service import TariffsService


_COMMERCIAL_DOCUMENTS = DocumentService.PROPOSAL_LINE_SCOPED_DOC_TYPES | B2C_NATIVE_DOCUMENT_TYPES | {
    "contract_amendment", "warranty_certificate",
}


async def _edit_locks(
    session: AsyncSession, scope: TenantScope, detail: dict[str, Any], *, writable: bool,
) -> tuple[bool, set[int | None]]:
    if (
        not writable
        or scope.demo_read_only
        or detail["workflow_type"] != "sales_installation"
        or detail["status"] not in {"new_lead", "negotiation"}
        or detail.get("equipment_status") == "issued"
        or detail.get("standard_install_kit_issued")
    ):
        return True, set()
    try:
        await require_unarchived_inbox(session, "order", detail["id"])
    except ValueError:
        return True, set()
    documents = (await session.execute(
        select(OrderDocument.doc_type, OrderDocument.proposal_id)
        .where(
            OrderDocument.order_id == detail["id"],
            OrderDocument.doc_type.in_(_COMMERCIAL_DOCUMENTS),
            or_(
                OrderDocument.tenant_id == scope.tenant_id,
                OrderDocument.tenant_id.is_(None),
            ),
            or_(
                OrderDocument.status.is_(None),  # legacy or externally received document
                OrderDocument.status.in_(("issued", "sent", "signed")),
            ),
        )
    )).all()
    return (
        any(doc_type != "offer" for doc_type, _ in documents),
        {proposal_id for doc_type, proposal_id in documents if doc_type == "offer"},
    )


def _proposals(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    proposals = list(detail["proposals"])
    active = [proposal for proposal in proposals if not proposal["is_archived"]]
    if active:
        selected = next((proposal for proposal in active if proposal["is_selected"]), active[0])
        return proposals, selected["id"]

    # A read-only projection preserves legacy lines and archived alternatives.
    # The first explicit command materializes this default under the order lock.
    status = (
        PROPOSAL_STATUS_SENT
        if detail.get("proposal_status") == PROPOSAL_STATUS_SENT and detail.get("proposal_sent_at")
        else PROPOSAL_STATUS_DRAFT
    )
    return [{
        "id": None, "name": "Основное", "status": status, "is_archived": False,
        "product_lines": [line for line in detail["product_lines"] if line["proposal_id"] is None],
        "service_lines": [line for line in detail["service_lines"] if line["proposal_id"] is None],
    }, *proposals], None


def _lines_editable(
    proposal: dict[str, Any], *, order_locked: bool, issued_offers: set[int | None],
) -> bool:
    return (
        not order_locked
        and not proposal["is_archived"]
        and None not in issued_offers
        and proposal["id"] not in issued_offers
        and proposal["status"] in {PROPOSAL_STATUS_DRAFT, PROPOSAL_STATUS_READY}
    )


def _selectable(proposal: dict[str, Any], selected_id: int | None, *, order_locked: bool) -> bool:
    return (
        not order_locked and not proposal["is_archived"]
        and proposal["id"] is not None and proposal["id"] != selected_id
        and proposal["status"] in {
            PROPOSAL_STATUS_DRAFT, PROPOSAL_STATUS_READY, PROPOSAL_STATUS_SENT, PROPOSAL_STATUS_APPROVED, "accepted",
        }
    )


async def _installation_options(
    session: AsyncSession, scope: TenantScope,
) -> list[BotOrderInstallationOption]:
    standards = await list_standard_tariffs(session, scope)
    if standards.price_book_revision is not None:
        return [
            BotOrderInstallationOption(
                id=f"standard:{standards.price_book_revision}:{tariff.code}",
                title=tariff.title, description=tariff.description, unit_price=money(tariff.price),
            )
            for tariff in standards.items if tariff.price > 0
        ]
    tariffs = await TariffsService.list_quick_add_tariffs(
        session, service_kind=ManagerTariffServiceKind.installation, limit=100, tenant_scope=scope,
    )
    return [
        BotOrderInstallationOption(
            id=f"tariff:{tariff.tariff_id}:{tariff.price}",
            title=tariff.title, description=tariff.full_description, unit_price=money(tariff.price),
        )
        for tariff in tariffs if tariff.tariff_id is not None and tariff.price > 0
    ]


def _display_line(line: dict[str, Any], title: str, description: str | None) -> dict[str, Any]:
    unit_price = money(line["price"])
    return {
        "title": title, "description": description, "quantity": line["quantity"],
        "unit_price": unit_price, "line_total": unit_price * line["quantity"],
    }


async def _attachment_claims(
    session: AsyncSession, proposals: list[dict[str, Any]],
) -> dict[int, set[int] | None]:
    revision_ids = {
        line["installation_estimate_revision_id"] for proposal in proposals for line in proposal["service_lines"]
        if line["installation_estimate_revision_id"] is not None
    }
    if not revision_ids:
        return {}
    rows = (await session.execute(
        select(InstallationEstimateRevision.id, InstallationEstimateRevision.snapshot)
        .where(InstallationEstimateRevision.id.in_(revision_ids))
    )).all()
    claims: dict[int, set[int] | None] = {}
    for revision_id, snapshot in rows:
        try:
            payload = InstallationPreviewPayload.model_validate(snapshot.get("input"))
        except ValueError:
            # An unrecognized historical attachment must stay intact.
            claims[revision_id] = None
            continue
        claims[revision_id] = {item.product_id for item in payload.installations if item.product_id is not None}
    return claims


def _bundled_installation(line: dict[str, Any]) -> bool:
    return bool(line["is_installation_included"] or line["installation_price"])


def _removable_line(
    proposal: dict[str, Any], detail: dict[str, Any], selected_id: int | None,
    line: dict[str, Any], *, is_product: bool, claims: dict[int, set[int] | None],
) -> bool:
    if not is_product:
        # Historical checkout did not store which service rows belonged to each
        # installed product. Keep those rows intact when this grouping is present.
        return line["installation_estimate_revision_id"] is None and not any(
            _bundled_installation(item) for item in proposal["product_lines"]
        )
    if proposal.get("multi_split_configuration") or _bundled_installation(line):
        return False
    if proposal["id"] == selected_id and (detail.get("equipment_status") == "reserved" or detail.get("linked_equipment_count")):
        return False
    for item in proposal["service_lines"]:
        revision_id = item["installation_estimate_revision_id"]
        if revision_id is not None:
            models = claims.get(revision_id)
            if models is None or line["product_id"] in models:
                return False
    return True


async def read_proposals(
    session: AsyncSession, actor: CommandActor, detail: dict[str, Any], *, writable: bool = True,
) -> dict[str, Any]:
    """Project authorized Manager detail with sale prices and capability flags."""
    scope = actor.tenant_scope
    order_locked, issued_offers = await _edit_locks(session, scope, detail, writable=writable)
    proposals, selected_id = _proposals(detail)
    editable_proposals = [
        item for item in proposals if _lines_editable(item, order_locked=order_locked, issued_offers=issued_offers)
    ]
    supplier_links = await OrderProductLineService.supply_referenced_ids(
        session, {line["id"] for proposal in editable_proposals for line in proposal["product_lines"]},
    )
    claims = await _attachment_claims(
        session, [item for item in editable_proposals if item["status"] == PROPOSAL_STATUS_DRAFT],
    )
    result = []
    installation_options = None
    for proposal in proposals:
        editable = _lines_editable(proposal, order_locked=order_locked, issued_offers=issued_offers)
        draft = editable and proposal["status"] == PROPOSAL_STATUS_DRAFT
        bundle = bool(proposal.get("multi_split_configuration"))
        can_append = draft and not bundle
        products = [
            {
                **_display_line(line, line["product_title"], line["client_description"]),
                "id": line["id"], "can_edit_quantity": editable and not bundle and line["id"] not in supplier_links,
                "can_edit_price": editable,
                "can_remove": draft and line["id"] not in supplier_links and _removable_line(
                    proposal, detail, selected_id, line, is_product=True, claims=claims,
                ),
                "product_id": line["product_id"], "is_installation_included": line["is_installation_included"],
            }
            for line in sorted(proposal["product_lines"], key=lambda line: line["id"])
        ]
        services = []
        for line in sorted(proposal["service_lines"], key=lambda line: line["id"]):
            can_edit_line = editable and line["installation_estimate_revision_id"] is None
            services.append({
                **_display_line(line, line["service_title"], line["description"]),
                "id": line["id"], "can_edit_quantity": can_edit_line, "can_edit_price": can_edit_line,
                "can_remove": draft and _removable_line(
                    proposal, detail, selected_id, line, is_product=False, claims=claims,
                ),
                "service_id": line["service_id"], "unit": line["unit"],
                "display_lines": [
                    _display_line(item, item["title"], item.get("description"))
                    for item in line.get("installation_display_lines", [])
                ],
            })
        equipment_total = sum((line["line_total"] for line in products), money(0))
        services_total = sum((line["line_total"] for line in services), money(0))
        if can_append and installation_options is None:
            installation_options = [option.model_dump() for option in await _installation_options(session, scope)]
        result.append({
            "id": proposal["id"], "name": proposal["name"], "status": proposal["status"],
            "is_selected": not proposal["is_archived"] and proposal["id"] == selected_id,
            "is_archived": proposal["is_archived"],
            "total_amount": equipment_total + services_total,
            "equipment_total": equipment_total, "services_total": services_total,
            "can_select": _selectable(proposal, selected_id, order_locked=order_locked),
            "can_add_equipment": can_append,
            "product_lines": products, "service_lines": services,
            "installation_options": installation_options if can_append else [],
        })
    return {"proposals": result, "selected_proposal_id": selected_id}


async def _append_equipment(
    session: AsyncSession, scope: TenantScope, order: Order, proposal: OrderProposal, change: BotOrderAddEquipment,
) -> None:
    quantities = {line.product_id: line.quantity for line in change.items}
    if any(link.proposal_id == proposal.id and link.product_id in quantities for link in order.product_links):
        raise HTTPException(409, "Модель уже есть в предложении. Измените количество в существующей позиции.")
    snapshots = await CatalogDecisionQueryService.get_product_snapshots(
        session, tenant_scope=scope, product_ids=list(quantities),
    )
    # The catalog supports out-of-stock models sold on order. Attaching a line
    # uses the current storefront price and does not reserve stock.
    if set(snapshots) != set(quantities) or any(snapshot.retail_price_byn <= 0 for snapshot in snapshots.values()):
        raise HTTPException(422, "Для части моделей нет действующей цены или доступа. Обновите подбор.")
    if any(snapshots[line.product_id].retail_price_byn != line.expected_unit_price_byn for line in change.items):
        raise HTTPException(409, "Цена оборудования изменилась. Обновите подбор и проверьте цены.")
    await CatalogDecisionOrderLineService.append(
        session, order_id=order.id, proposal_id=proposal.id,
        product_ids=list(quantities), snapshots=snapshots, quantities=quantities,
    )


async def _append_installation(
    session: AsyncSession, scope: TenantScope, order: Order, proposal: OrderProposal, change: BotOrderAddInstallation,
) -> None:
    options = await _installation_options(session, scope)
    option = next((item for item in options if item.id == change.option_id), None)
    if option is None:
        raise HTTPException(409, "Тариф монтажа изменился или недоступен. Обновите заказ.")
    session.add(OrderServiceLink(
        order_id=order.id, proposal_id=proposal.id, title=option.title,
        description=option.description, quantity=change.quantity,
        price=writable_service_money(option.unit_price),
    ))


async def _mutate_line(
    session: AsyncSession, order: Order, proposal: OrderProposal, change: BotOrderUpdateLine | BotOrderRemoveLine,
    *, source: dict[str, Any], detail: dict[str, Any], selected_id: int | None,
) -> None:
    is_product = change.line_kind == "product"
    model = OrderProductLink if is_product else OrderServiceLink
    # Supplier requests may reference a product independently of the parent
    # order lock. Serialize with their FK before checking for references.
    line = await session.scalar(
        select(model).where(
            model.id == change.line_id, model.order_id == order.id, model.proposal_id == proposal.id,
        ).with_for_update().execution_options(populate_existing=True)
    )
    if line is None:
        raise HTTPException(404, "Позиция предложения не найдена.")
    if isinstance(line, OrderServiceLink) and line.installation_estimate_revision_id is not None:
        raise HTTPException(409, "Позицию из сохранённой сметы можно изменить в Kitlane.")
    removing = isinstance(change, BotOrderRemoveLine)
    quantity_changed = not removing and change.quantity is not None and change.quantity != line.quantity
    if is_product and (removing or quantity_changed) and await OrderProductLineService.supply_referenced_ids(session, {line.id}):
        raise HTTPException(409, "Позиция включена в заявку поставщику.")
    if removing:
        lines = source["product_lines"] if is_product else source["service_lines"]
        display = next((item for item in lines if item["id"] == line.id), None)
        claims = await _attachment_claims(session, [source]) if is_product else {}
        if display is None or not _removable_line(source, detail, selected_id, display, is_product=is_product, claims=claims):
            raise HTTPException(409, "Позиция связана с оборудованием или работами. Измените состав в Kitlane.")
        await session.delete(line)
        return
    if quantity_changed:
        if is_product and source.get("multi_split_configuration"):
            raise HTTPException(409, "Состав мультисплита меняется в Kitlane.")
        line.quantity = change.quantity
    if change.unit_price is not None:
        line.price = int(change.unit_price) if is_product else writable_service_money(change.unit_price)
    session.add(line)


async def apply_proposal(
    session: AsyncSession, actor: CommandActor, order_id: int, change: BotProposalChange,
    detail: dict[str, Any],
) -> None:
    """Apply one proposal command within the caller's locked order transaction."""
    if detail["id"] != order_id:
        raise HTTPException(404, "Заказ не найден.")
    scope = actor.tenant_scope
    order_locked, issued_offers = await _edit_locks(session, scope, detail, writable=True)
    proposals, selected_id = _proposals(detail)
    target = next((item for item in proposals if item["id"] == change.proposal_id and not item["is_archived"]), None)
    if target is None:
        raise HTTPException(404, "Предложение не найдено.")
    selecting = isinstance(change, BotOrderSelectProposal)
    if selecting:
        allowed = _selectable(target, selected_id, order_locked=order_locked)
    else:
        allowed = _lines_editable(target, order_locked=order_locked, issued_offers=issued_offers)
        if not isinstance(change, BotOrderUpdateLine):
            allowed = allowed and target["status"] == PROPOSAL_STATUS_DRAFT
    if not allowed:
        raise HTTPException(409, "Предложение уже недоступно для этого действия.")

    order = await OrderProposalCommandService._load_order_for_write(session, order_id, tenant_scope=scope)
    proposal = OrderService._selected_proposal(order) if change.proposal_id is None else next(
        (item for item in order.proposals if item.id == change.proposal_id and not item.is_archived), None,
    )
    if proposal is None or (change.proposal_id is None and len([item for item in order.proposals if not item.is_archived]) != 1):
        raise HTTPException(409, "Предложения обновились. Откройте заказ снова.")
    if selecting:
        await OrderProposalCommandService.apply_selection(session, order, proposal)
        return

    await guard_lines(session, order_id, proposal.id)
    bundle = bool(target.get("multi_split_configuration"))
    if isinstance(change, (BotOrderUpdateLine, BotOrderRemoveLine)):
        await _mutate_line(session, order, proposal, change, source=target, detail=detail, selected_id=selected_id)
    else:
        if bundle:
            raise HTTPException(409, "Состав мультисплита меняется в Kitlane.")
        if isinstance(change, BotOrderAddEquipment):
            await _append_equipment(session, scope, order, proposal, change)
        else:
            await _append_installation(session, scope, order, proposal, change)

    await session.flush()
    await InstallationEstimateConfirmationService.validate_attached_claims(session, order_id, proposal.id)
    await OrderService._refresh_order_financials(session, order)
    session.add(order)
