from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from models import OrderProductLink


DEFAULT_COUNTRY = "Китай"


def build_logistics_rows(
    product_links: Sequence[OrderProductLink],
) -> list[dict[str, str]]:
    """Expand saved product composition into reproducible paper-waybill rows."""

    rows: list[dict[str, str]] = []
    for link in product_links:
        product = link.product
        parent_title = str(
            link.title_snapshot or getattr(product, "title", "") or "Товар"
        )
        parent_quantity = _positive_int(link.quantity, 1)
        parent_price = _decimal(link.price)
        components = _order_components(link.logistics_components)
        if components:
            components = _balance_saved_components(components, parent_price)
        else:
            components = _catalog_components(
                getattr(product, "specs", None), parent_price
            )
        if not components:
            components = [
                {
                    "title": parent_title,
                    "country": _product_country(getattr(product, "specs", None))
                    or DEFAULT_COUNTRY,
                    "unit": "шт.",
                    "quantity_per_parent": 1,
                    "unit_price": parent_price,
                }
            ]

        for component in components:
            quantity = parent_quantity * int(component["quantity_per_parent"])
            unit_price = _decimal(component["unit_price"])
            amount = unit_price * quantity
            rows.append(
                {
                    "line.number": str(len(rows) + 1),
                    "line.title": str(component["title"]),
                    "line.kind": "product",
                    "line.country": str(component["country"]),
                    "line.unit": str(component["unit"]),
                    "line.quantity": str(quantity),
                    "line.unit_price": _money(unit_price),
                    "line.amount": _money(amount),
                    "line.vat_label": "",
                    "line.seats": str(quantity),
                    "line.mass": "0.00",
                    "line.note": "—",
                    "line.amount_raw": str(amount),
                    "line.quantity_raw": str(quantity),
                    "line.mass_raw": "0",
                }
            )
    return rows


def _order_components(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        title = _clean(item.get("title"))
        if not title:
            continue
        result.append(
            {
                "title": title,
                "country": _clean(item.get("country")) or DEFAULT_COUNTRY,
                "unit": _clean(item.get("unit")) or "шт.",
                "quantity_per_parent": _positive_int(
                    item.get("quantity_per_parent"), 1
                ),
                "unit_price": _decimal(item.get("unit_price")),
            }
        )
    return result


def _catalog_components(
    raw_specs: object, parent_price: Decimal
) -> list[dict[str, object]]:
    if not isinstance(raw_specs, Mapping):
        return []
    raw = raw_specs.get("logistics_components")
    if not isinstance(raw, list):
        return []
    components: list[dict[str, object]] = []
    weights: list[Decimal] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        title = _clean(item.get("title"))
        if not title:
            continue
        components.append(
            {
                "title": title,
                "country": _clean(item.get("country"))
                or _product_country(raw_specs)
                or DEFAULT_COUNTRY,
                "unit": _clean(item.get("unit")) or "шт.",
                "quantity_per_parent": _positive_int(
                    item.get("quantity_per_parent"), 1
                ),
                "unit_price": Decimal("0"),
            }
        )
        weights.append(max(Decimal("0"), _decimal(item.get("price_weight") or 1)))
    if not components:
        return []
    if not any(weights):
        weights = [Decimal("1")] * len(components)
    remaining = parent_price
    total_weight = sum(weights, Decimal("0"))
    for index, component in enumerate(components):
        quantity = Decimal(int(component["quantity_per_parent"]))
        if index == len(components) - 1:
            component_total = remaining
        else:
            component_total = (parent_price * weights[index] / total_weight).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            remaining -= component_total
        component["unit_price"] = component_total / quantity
    return components


def _balance_saved_components(
    components: list[dict[str, object]],
    parent_price: Decimal,
) -> list[dict[str, object]]:
    per_parent = sum(
        (
            _decimal(item["unit_price"]) * int(item["quantity_per_parent"])
            for item in components
        ),
        Decimal("0"),
    )
    if per_parent == parent_price:
        return components
    last = components[-1]
    quantity = Decimal(int(last["quantity_per_parent"]))
    last["unit_price"] = _decimal(last["unit_price"]) + (
        (parent_price - per_parent) / quantity
    )
    return components


def _product_country(raw_specs: object) -> str:
    if not isinstance(raw_specs, Mapping):
        return ""
    for key in (
        "country",
        "country_of_origin",
        "Страна производства",
        "Страна-производитель",
    ):
        value = _clean(raw_specs.get(key))
        if value:
            return value
    return ""


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
