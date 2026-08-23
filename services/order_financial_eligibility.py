"""Shared financial eligibility rules for CRM orders.

Order totals are commercial expectations until the order reaches an explicit
financially meaningful state. Payments tied to rejected orders are excluded
from management revenue and reconciliation figures as failed sales.
"""

from __future__ import annotations

from sqlalchemy import and_, or_

from models.common import ClosingResult, OrderStatus
from models.order import Order


AWAITING_PAYMENT = "awaiting_payment"


def is_successful_order(order: Order) -> bool:
    """Return whether an order may create a debit in a reconciliation act."""

    status = getattr(order.status, "value", order.status)
    closing_result = getattr(order.closing_result, "value", order.closing_result)
    return (
        status == OrderStatus.CLOSED.value
        and closing_result == ClosingResult.WON.value
    )


def collectible_order_clause():
    """SQL condition for an open order whose balance is a credible receivable.

    Execution means the company has already accepted the work.  During
    negotiation, only the explicit awaiting-payment substage is sufficiently
    concrete; offers, visits, follow-ups and unsigned proposals are not debt.
    """

    return or_(
        Order.status == OrderStatus.EXECUTION,
        and_(
            Order.status == OrderStatus.NEGOTIATION,
            Order.negotiation_status == AWAITING_PAYMENT,
        ),
    )


def financially_committed_order_clause():
    """SQL condition for payments that count as management revenue."""

    return or_(
        collectible_order_clause(),
        and_(
            Order.status == OrderStatus.CLOSED,
            Order.closing_result == ClosingResult.WON.value,
        ),
    )
