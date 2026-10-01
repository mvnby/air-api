"""Build monetary table rows from the selected document lines."""

from decimal import Decimal
from typing import Mapping, Sequence

from models import OrderProductLink, OrderServiceLink
from services.order_product_description import product_line_document_title
from services.order_service_description import service_line_document_title
from .value_formatters import money


def line_rows(
    product_links: Sequence[OrderProductLink],
    service_lines: Sequence[tuple[OrderServiceLink, int]],
    installation_descriptions: Mapping[int, str] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in product_links:
        quantity = int(item.quantity or 0)
        unit_price = Decimal(str(item.price or 0))
        rows.append(
            line_row(
                len(rows) + 1,
                title=product_line_document_title(item),
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
                title=service_line_document_title(item, installation_descriptions),
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
