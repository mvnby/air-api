"""Limits shared by Manager and Telegram when reserving equipment from an order."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.supplier import SupplierOffer, SupplyRequest, SupplyRequestLine
from services.supplier_availability import classify_availability


RESERVATION_TIMEZONE = ZoneInfo("Europe/Minsk")


def reservation_now() -> datetime:
    # Manager's persisted reservation deadlines are local wall times.
    return datetime.now(RESERVATION_TIMEZONE).replace(tzinfo=None)


def reservation_line_status(line: SupplyRequestLine, request: SupplyRequest, now: datetime) -> str:
    if line.status == "received":
        return "received"
    if request.status == "canceled" or line.status == "canceled":
        return "canceled"
    if line.status == "reserved" and line.reserved_until is not None and line.reserved_until <= now:
        return "expired"
    return line.status


def reserved_order_quantity(line: SupplyRequestLine, request: SupplyRequest, now: datetime) -> int:
    if reservation_line_status(line, request, now) in {"canceled", "expired"}:
        return max(0, min(line.received_qty, line.qty))
    return line.qty


async def order_line_commitments(session: AsyncSession, line_ids: list[int], now: datetime) -> dict[int, int]:
    rows = (await session.execute(
        select(SupplyRequestLine, SupplyRequest)
        .join(SupplyRequest, SupplyRequest.id == SupplyRequestLine.request_id)
        .where(SupplyRequestLine.order_product_link_id.in_(line_ids))
        .execution_options(populate_existing=True)
    )).all()
    result: dict[int, int] = defaultdict(int)
    for line, request in rows:
        result[line.order_product_link_id] += reserved_order_quantity(line, request, now)
    return result


async def supplier_offer_commitments(
    session: AsyncSession, offers: list[SupplierOffer], now: datetime,
) -> dict[int, int]:
    if not offers:
        return {}
    rows = (await session.execute(
        select(SupplierOffer.id, func.sum(func.greatest(SupplyRequestLine.qty - SupplyRequestLine.received_qty, 0)))
        .select_from(SupplierOffer)
        .join(SupplyRequest, SupplyRequest.supplier_id == SupplierOffer.supplier_id)
        .join(SupplyRequestLine, and_(
            SupplyRequestLine.request_id == SupplyRequest.id,
            SupplyRequestLine.supplier_offer_external_id == SupplierOffer.external_id,
        ))
        .where(
            SupplierOffer.id.in_([offer.id for offer in offers]),
            SupplyRequest.status != "canceled",
            SupplyRequestLine.status.not_in(("canceled", "received")),
            or_(
                SupplyRequestLine.status != "reserved",
                SupplyRequestLine.reserved_until.is_(None),
                SupplyRequestLine.reserved_until > now,
            ),
        )
        .group_by(SupplierOffer.id)
    )).all()
    return {offer_id: int(qty) for offer_id, qty in rows}


def reservable_offer_quantity(offer: SupplierOffer, committed: int) -> int:
    if not offer.is_active or classify_availability(offer.qty_raw) in {"incoming", "out_of_stock"}:
        return 0
    return max(0, offer.qty - committed)
