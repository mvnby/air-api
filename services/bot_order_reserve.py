"""Reuse supply requests for order-scoped Telegram reservations."""

from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_reserve import (
    BotConfirmReserveRequest,
    BotCreateReserveRequest,
    BotMarkReserveRequestSent,
    BotOrderReserveState,
    BotReserveCandidate,
    BotReserveChange,
    BotReserveLine,
    BotReserveRequest,
    BotSetOrderReserveStatus,
)
from core.command_actor import CommandActor
from models import OrderProductLink, Product
from models.common import EquipmentStatus, SupplyRequestStatus
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource, SupplyRequest, SupplyRequestLine
from services.inbox_eligibility import require_unarchived_inbox
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.order_workflow_revision import bump_order_workflow_revision
from services.supply_request_service import SupplyRequestService
from services.supply_reservation_capacity import (
    RESERVATION_TIMEZONE, reservable_offer_quantity, reservation_line_status,
    reservation_now, reserved_order_quantity, supplier_offer_commitments,
)
from services.tenant_entity_access_service import TenantEntityAccessService


_NO_ACCESS = "Резерв поставщика доступен только оператору платформы в системной компании."
_RESERVED_OR_LATER = frozenset({
    SupplyRequestStatus.RESERVED, SupplyRequestStatus.READY_FOR_PICKUP,
    SupplyRequestStatus.PICKED_UP, SupplyRequestStatus.RECEIVED,
})


async def _can_access(session: AsyncSession, actor: CommandActor, *, lock: bool = False) -> bool:
    if not actor.tenant_scope.is_system or actor.tenant_scope.demo_read_only:
        return False
    # Match the Manager supply ACL. A tenant owner or manager role alone has no supplier access.
    owner = await LegacyOwnerAuthGuard.state(session, for_share=lock)
    return LegacyOwnerAuthGuard.allows_bound_staff(owner, staff_user_id=actor.staff_user_id)


async def _unavailable_reason(session: AsyncSession, detail: dict) -> str | None:
    if detail["status"] not in {"negotiation", "execution"}:
        return "Заказ закрыт. История поставок доступна для просмотра."
    if detail.get("equipment_status") == "issued":
        return "Оборудование уже выдано."
    try:
        await require_unarchived_inbox(session, "order", detail["id"])
    except ValueError as exc:
        return str(exc)
    return None


def _selected_lines(detail: dict) -> list[dict]:
    active = [proposal for proposal in detail["proposals"] if not proposal["is_archived"]]
    if active:
        selected = next((proposal for proposal in active if proposal["is_selected"]), active[0])
        return selected["product_lines"]
    return [line for line in detail["product_lines"] if line["proposal_id"] is None]


def _can_set_order_status(lines: list[dict], status: str | None) -> bool:
    return status == "reserved" or any(line["quantity"] > 0 for line in lines)


def _supply_rows(line_ids):
    return (
        select(SupplyRequestLine, SupplyRequest, Supplier.name)
        .join(SupplyRequest, SupplyRequest.id == SupplyRequestLine.request_id)
        .join(Supplier, Supplier.id == SupplyRequest.supplier_id)
        .where(SupplyRequestLine.order_product_link_id.in_(line_ids))
        .order_by(SupplyRequestLine.id.desc())
        .execution_options(populate_existing=True)
    )


def _remaining(rows, quantity: int, now: datetime) -> int:
    occupied = sum(reserved_order_quantity(line, request, now) for line, request, _supplier_name in rows)
    return max(0, quantity - occupied)


def _offer_query(product_ids):
    return (
        select(ProductSupplierMapping.product_id, SupplierOffer, Supplier.name)
        .select_from(ProductSupplierMapping)
        .join(SupplierOffer, and_(
            SupplierOffer.supplier_id == ProductSupplierMapping.supplier_id,
            SupplierOffer.external_id == ProductSupplierMapping.external_id,
        ))
        .join(Supplier, Supplier.id == SupplierOffer.supplier_id)
        .outerjoin(SupplierPriceSource, and_(
            SupplierPriceSource.id == SupplierOffer.source_id,
            SupplierPriceSource.supplier_id == SupplierOffer.supplier_id,
        ))
        .where(
            ProductSupplierMapping.product_id.in_(product_ids),
            ProductSupplierMapping.is_active.is_(True),
            SupplierOffer.is_active.is_(True),
            Supplier.is_active.is_(True),
            or_(SupplierOffer.source_id.is_(None), SupplierPriceSource.is_active.is_(True)),
        )
        .order_by(Supplier.priority, Supplier.name, SupplierOffer.id)
        .execution_options(populate_existing=True)
    )


def _message(line: SupplyRequestLine, model: str) -> str:
    code = f" (код {line.supplier_offer_external_id})" if line.supplier_offer_external_id else ""
    return f"Здравствуйте! Подтвердите наличие и резерв, пожалуйста: {model}{code} — {line.qty} шт."


def _can_confirm(line: SupplyRequestLine, request: SupplyRequest, *, eligible: bool) -> bool:
    return (
        eligible and line.source_type == "order_line"
        and request.intent == "reserve" and request.status in {"draft", "awaiting_reply", "reserved"}
        and line.status in {"draft", "awaiting_reply"} and line.qty > 0 and not line.received_qty
    )


def _can_mark_sent(line: SupplyRequestLine, request: SupplyRequest, *, eligible: bool, count: int) -> bool:
    return (
        _can_confirm(line, request, eligible=eligible) and count == 1
        and request.status == "draft" and line.status == "draft" and request.supplier_message_sent_at is None
    )


async def read_reserve(session: AsyncSession, actor: CommandActor, detail: dict) -> BotOrderReserveState:
    demo = actor.tenant_scope.demo_read_only
    unavailable_reason = (
        "В демонстрационном режиме изменения недоступны."
        if demo else await _unavailable_reason(session, detail)
    )
    status = detail.get("equipment_status")
    lines = _selected_lines(detail)
    supplier_access = await _can_access(session, actor)
    state = BotOrderReserveState(
        enabled=unavailable_reason is None,
        unavailable_reason=unavailable_reason,
        manager_status=status,
        can_set_order_status=unavailable_reason is None and _can_set_order_status(lines, status),
        supplier_access=supplier_access,
        supplier_access_reason=_NO_ACCESS if not supplier_access and not demo else None,
    )
    if not supplier_access or not lines:
        state.lines = [
            BotReserveLine(
                id=line["id"], title=line["product_title"], quantity=line["quantity"],
                remaining_quantity=None, candidates=[], requests=[],
            )
            for line in lines
        ]
        return state

    now = reservation_now()
    order_lines = defaultdict(list)
    for row in (await session.execute(_supply_rows([line["id"] for line in lines]))).all():
        order_lines[row[0].order_product_link_id].append(row)
    offer_rows = []
    request_sizes = {}
    model_names = {}
    if unavailable_reason is None:
        offer_rows = (
            await session.execute(_offer_query({line["product_id"] for line in lines if line["product_id"]}))
        ).all()
        request_ids = {req.id for rows in order_lines.values() for _, req, _ in rows if req.intent == "reserve"}
        if request_ids:
            request_sizes = dict(
                (await session.execute(
                    select(SupplyRequestLine.request_id, func.count())
                    .where(SupplyRequestLine.request_id.in_(request_ids))
                    .group_by(SupplyRequestLine.request_id)
                )).tuples().all()
            )
            model_names = dict((await session.execute(
                select(Product.id, Product.title).where(Product.id.in_({line["product_id"] for line in lines})),
            )).tuples().all())
    offers_by_product = defaultdict(list)
    offer_keys = set()
    for product_id, offer, supplier_name in offer_rows:
        offers_by_product[product_id].append((offer, supplier_name))
        offer_keys.add((product_id, offer.supplier_id, offer.external_id))
    pending = await supplier_offer_commitments(session, [row[1] for row in offer_rows], now)

    result = []
    for line in lines:
        rows = order_lines[line["id"]]
        remaining = _remaining(rows, line["quantity"], now)
        candidates = []
        if remaining:
            for offer, supplier_name in offers_by_product[line["product_id"]]:
                available = min(remaining, reservable_offer_quantity(offer, pending.get(offer.id, 0)))
                if available:
                    candidates.append(BotReserveCandidate(
                        offer_id=offer.id, supplier_name=supplier_name, offer_title=offer.title_raw,
                        offer_code=offer.external_id, max_quantity=available,
                    ))
        requests = []
        for item, request, supplier_name in rows:
            eligible = (
                line["product_id"] == item.product_id
                and (item.product_id, request.supplier_id, item.supplier_offer_external_id) in offer_keys
                and item.qty <= _remaining([row for row in rows if row[0].id != item.id], line["quantity"], now)
            )
            mark_sent = _can_mark_sent(item, request, eligible=eligible, count=request_sizes.get(request.id, 0))
            requests.append(BotReserveRequest(
                id=item.id, request_id=request.id, supplier_name=supplier_name, quantity=item.qty,
                status=reservation_line_status(item, request, now), intent=request.intent,
                reserved_until=item.reserved_until.replace(tzinfo=RESERVATION_TIMEZONE) if item.reserved_until else None,
                supplier_message=_message(item, model_names[item.product_id]) if mark_sent else None, can_mark_sent=mark_sent,
                can_confirm=_can_confirm(item, request, eligible=eligible),
            ))
        result.append(BotReserveLine(
            id=line["id"], title=line["product_title"], quantity=line["quantity"],
            remaining_quantity=remaining, candidates=candidates, requests=requests,
        ))
    state.lines = result
    return state


async def _create_request(session, actor, link, model, rows, change: BotCreateReserveRequest) -> None:
    candidate = (
        await session.execute(
            _offer_query([link.product_id])
            .where(SupplierOffer.id == change.offer_id)
            .with_for_update(of=(SupplierOffer, ProductSupplierMapping, Supplier))
        )
    ).one_or_none()
    if candidate is None:
        raise HTTPException(409, "Предложение поставщика больше недоступно для этой модели.")
    _, offer, _ = candidate
    # Lock the offer before counting commitments from concurrent orders using the same stock.
    now = reservation_now()
    pending = await supplier_offer_commitments(session, [offer], now)
    maximum = min(_remaining(rows, link.quantity, now), reservable_offer_quantity(offer, pending.get(offer.id, 0)))
    if change.quantity > maximum:
        raise HTTPException(409, "Изменилось доступное количество. Обновите заказ и проверьте остаток.")
    await SupplyRequestService.stage_request(session, {
        "supplier_id": offer.supplier_id,
        "intent": "reserve",
        "lines": [{
            "order_product_link_id": link.id, "product_id": link.product_id, "source_type": "order_line",
            "title": model, "qty": change.quantity,
            "supplier_offer_external_id": offer.external_id, "supplier_offer_title": offer.title_raw,
            "unit_cost": await SupplyRequestService._offer_cost_decimal(session, offer),
        }],
    }, created_by=actor.username)


async def _change_request(session, link, model, rows, change) -> None:
    row = next((row for row in rows if row[0].id == change.request_line_id), None)
    if row is None:
        raise HTTPException(409, "Заявка не найдена в этой строке заказа.")
    item, request, _ = row
    await session.refresh(request, with_for_update=True)
    items = (await session.execute(
        select(SupplyRequestLine).where(SupplyRequestLine.request_id == request.id)
        .order_by(SupplyRequestLine.id).with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    if not any(current.id == item.id for current in items) or item.order_product_link_id != link.id:
        raise HTTPException(409, "Заявка больше не относится к этой строке заказа.")
    matching_offer = (
        await session.execute(
            _offer_query([link.product_id])
            .where(SupplierOffer.supplier_id == request.supplier_id, SupplierOffer.external_id == item.supplier_offer_external_id)
            .with_for_update(read=True, of=(SupplierOffer, ProductSupplierMapping, Supplier))
        )
    ).one_or_none()
    now = reservation_now()
    eligible = (
        matching_offer is not None and item.product_id == link.product_id
        and item.qty <= _remaining([row for row in rows if row[0].id != item.id], link.quantity, now)
    )
    if isinstance(change, BotMarkReserveRequestSent):
        if not _can_mark_sent(item, request, eligible=eligible, count=len(items)):
            raise HTTPException(409, "Заявка уже изменилась. Проверьте её состояние.")
        await SupplyRequestService.stage_supplier_message_sent(session, request, _message(item, model))
        return
    if not _can_confirm(item, request, eligible=eligible):
        raise HTTPException(409, "Эту заявку больше нельзя подтвердить. Проверьте её состояние.")
    reserved_until = None
    if change.reserved_until is not None:
        try:
            reserved_until = change.reserved_until.astimezone(RESERVATION_TIMEZONE).replace(tzinfo=None)
        except (OverflowError, ValueError) as exc:
            raise HTTPException(400, "Срок резерва указан неверно.") from exc
        if reserved_until <= now:
            raise HTTPException(400, "Срок резерва должен быть в будущем.")
    await SupplyRequestService.stage_line_update(session, item, {
        "status": "reserved", "reserved_until": reserved_until,
    })
    if all(other.status in _RESERVED_OR_LATER or other.status == "canceled" for other in items):
        request.status = "reserved"


async def apply_reserve(
    session: AsyncSession, actor: CommandActor, order_id: int, change: BotReserveChange, detail: dict,
) -> None:
    """Apply one reservation mutation under the order desk command transaction."""
    order_status_change = isinstance(change, BotSetOrderReserveStatus)
    if actor.tenant_scope.demo_read_only:
        raise HTTPException(403, "В демонстрационном режиме изменения недоступны.")
    if not order_status_change and not await _can_access(session, actor, lock=True):
        raise HTTPException(403, _NO_ACCESS)
    order = await TenantEntityAccessService.get_order(
        session, order_id, tenant_scope=actor.tenant_scope, for_update=True, populate_existing=True,
    )
    if order is None or detail["id"] != order_id:
        raise HTTPException(404, "Заказ не найден.")
    locked_detail = {**detail, "status": order.status, "equipment_status": order.equipment_status}
    reason = await _unavailable_reason(session, locked_detail)
    if reason:
        raise HTTPException(409, reason)
    selected_lines = _selected_lines(detail)
    if order_status_change:
        if not _can_set_order_status(selected_lines, order.equipment_status):
            raise HTTPException(409, "В выбранном предложении нет оборудования.")
        if order.equipment_status != change.status:
            order.equipment_status = EquipmentStatus(change.status)
            await bump_order_workflow_revision(session, order)
        return

    line = next((line for line in selected_lines if line["id"] == change.line_id), None)
    if line is None:
        raise HTTPException(409, "Строка не входит в выбранное предложение заказа.")
    link = (
        await session.execute(
            select(OrderProductLink).where(OrderProductLink.id == change.line_id, OrderProductLink.order_id == order_id)
            .with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if (
        link is None or not link.product_id or link.quantity <= 0
        or link.proposal_id != line["proposal_id"] or link.product_id != line["product_id"]
    ):
        raise HTTPException(409, "Строка заказа изменилась. Обновите карточку заказа.")
    model = await session.scalar(select(Product.title).where(Product.id == link.product_id))
    if model is None:
        raise HTTPException(409, "Модель больше не найдена в каталоге.")
    rows = (await session.execute(_supply_rows([link.id]))).all()
    if isinstance(change, BotCreateReserveRequest):
        await _create_request(session, actor, link, model, rows, change)
    else:
        await _change_request(session, link, model, rows, change)
    await bump_order_workflow_revision(session, order)
