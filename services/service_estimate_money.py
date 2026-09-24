"""Cent-exact estimate totals and deterministic discount allocation."""

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Sequence


CENT = Decimal("0.01")
LEGACY_FLOAT_TOLERANCE = Decimal("0.0000001")


def decimal_value(value: object) -> Decimal:
    result = Decimal(str(value if value is not None else 0))
    if not result.is_finite():
        raise ValueError("Money must be finite")
    return result


def money(value: object) -> Decimal:
    return decimal_value(value).quantize(CENT, rounding=ROUND_HALF_UP)


def exact_money(value: object) -> Decimal:
    result = decimal_value(value)
    if result < 0 or result != result.quantize(CENT):
        raise ValueError("Money must be non-negative and have at most two decimals")
    return result


def writable_service_money(value: object) -> Decimal:
    """Fence fractional writes until all API nodes can read decimal service prices."""
    from core.config import settings

    result = exact_money(value)
    if result != result.to_integral_value() and not settings.EXACT_SERVICE_MONEY_WRITES_ENABLED:
        raise ValueError(
            "Запись копеек услуг временно отключена; сохранение не выполнено"
        )
    return result


def snapshot_money(value: object) -> Decimal:
    """Tolerate only binary-float dust in old saved snapshots."""
    result = decimal_value(value)
    rounded = money(result)
    if result < 0 or abs(result - rounded) > LEGACY_FLOAT_TOLERANCE:
        raise ValueError("Saved estimate has money outside cent precision")
    return rounded


def allocate_discount(gross: Sequence[Decimal], discount: Decimal) -> list[Decimal]:
    """Return net rows; split remaining cents by largest remainder, then index."""
    amounts = [exact_money(value) for value in gross]
    reduction = exact_money(discount)
    subtotal = sum(amounts, Decimal("0.00"))
    if reduction > subtotal:
        raise ValueError("Discount exceeds estimate subtotal")
    if not subtotal or not reduction:
        return amounts

    shares = [reduction * amount / subtotal for amount in amounts]
    allocated = [share.quantize(CENT, rounding=ROUND_FLOOR) for share in shares]
    remaining_cents = int((reduction - sum(allocated, Decimal("0.00"))) / CENT)
    order = sorted(range(len(amounts)), key=lambda index: (-(shares[index] - allocated[index]), index))
    for index in order[:remaining_cents]:
        allocated[index] += CENT
    result = [amount - portion for amount, portion in zip(amounts, allocated)]
    if any(value < 0 for value in result) or sum(result, Decimal("0.00")) != subtotal - reduction:
        raise ValueError("Discount allocation does not reconcile")
    return result
