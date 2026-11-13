"""Project refreshed order finances into the currency of a bank receipt."""

from dataclasses import dataclass
from math import isfinite

from models import Order, PaymentCurrency


@dataclass(frozen=True)
class ReceiptOrderAmounts:
    total_amount: float
    total_payments: float

    @property
    def balance_due(self) -> float:
        return max(0.0, self.total_amount - self.total_payments)


def receipt_order_amounts(order: Order, currency: PaymentCurrency) -> ReceiptOrderAmounts | None:
    """Reuse the saved fixed-price accounting; never obtain or invent an FX rate.

    Callers refresh relationships and calculate order totals first. A foreign
    receipt is usable only when that order has a matching positive fixed price
    and a positive BYN value from which calculate_totals can account for payments.
    """
    if currency == PaymentCurrency.BYN:
        return ReceiptOrderAmounts(float(order.total_amount or 0), float(order.total_payments or 0))
    target_amount = float(order.target_currency_amount or 0)
    byn_amount = float(order.total_amount or 0)
    if (
        order.target_currency != currency
        or not isfinite(target_amount)
        or target_amount <= 0
        or not isfinite(byn_amount)
        or byn_amount <= 0
    ):
        return None
    return ReceiptOrderAmounts(target_amount, float(order.target_currency_payments or 0))


def require_receipt_order_amounts(order: Order, currency: PaymentCurrency) -> ReceiptOrderAmounts:
    amounts = receipt_order_amounts(order, currency)
    if amounts is None:
        raise ValueError(
            f"Order #{order.id} requires a positive fixed price in the bank receipt currency"
        )
    return amounts
