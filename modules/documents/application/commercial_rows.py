"""Build monetary table rows from the selected document lines."""

from decimal import Decimal
from typing import Sequence

from models import OrderProductLink, OrderServiceLink
from .value_formatters import money


def line_rows(
    product_links: Sequence[OrderProductLink],
    service_lines: Sequence[tuple[OrderServiceLink, int]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in product_links:
        quantity = int(item.quantity or 0)
        unit_price = Decimal(str(item.price or 0))
        rows.append(
            line_row(
                len(rows) + 1,
                title=str(
                    item.title_snapshot
                    or getattr(item.product, "title", "")
                    or "Товар"
                ),
                kind="product",
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    for item, quantity in service_lines:
        unit_price = Decimal(str(item.price or 0))
        rows.append(
            line_row(
                len(rows) + 1,
                title=str(
                    item.title or getattr(item.service, "title", "") or "Услуга"
                ),
                kind="service",
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    return rows


def line_row(
    index: int,
    *,
    title: str,
    kind: str,
    quantity: int,
    unit_price: Decimal,
) -> dict[str, str]:
    amount = unit_price * quantity
    return {
        "line.number": str(index),
        "line.title": title,
        "line.kind": kind,
        "line.unit": "шт.",
        "line.quantity": str(quantity),
        "line.unit_price": money(unit_price),
        "line.amount": money(amount),
        "line.country": "",
        "line.vat_label": "",
        "line.seats": "",
        "line.mass": "",
        "line.note": "",
        "line.amount_raw": str(amount),
        "line.quantity_raw": str(quantity),
        "line.mass_raw": "0",
    }
