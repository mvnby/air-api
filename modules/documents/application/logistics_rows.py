from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from models import OrderProductLink
from modules.documents.domain.waybill_composition import (
    WaybillComponent,
    WaybillComposition,
    WaybillCompositionSource,
    WaybillSourceLine,
)


def waybill_composition_source(
    product_links: Sequence[OrderProductLink],
) -> WaybillCompositionSource:
    """Return the same scoped source to the editor and to the final draft check."""
    groups = []
    for link in sorted(product_links, key=lambda item: item.id):
        product = link.product
        if link.quantity is None or link.quantity <= 0:
            raise ValueError("Укажите положительное количество товара в предложении")
        parent_price = _decimal(link.price)
        saved = _order_components(link.logistics_components)
        components = saved or _catalog_components(
            getattr(product, "specs", None), parent_price
        )
        groups.append(
            WaybillSourceLine(
                order_product_line_id=link.id,
                product_id=link.product_id,
                title=link.title_snapshot or getattr(product, "title", "") or "Товар",
                country=_product_country(getattr(product, "specs", None)),
                quantity=link.quantity,
                unit_price=_money(parent_price),
                components=[
                    WaybillComponent(
                        **{**item, "unit_price": _money(item["unit_price"])}
                    )
                    for item in components
                ]
                or None,
            )
        )
    encoded = json.dumps(
        [group.model_dump() for group in groups],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return WaybillCompositionSource(
        source_revision=hashlib.sha256(encoded).hexdigest(), lines=groups
    )


def build_logistics_rows(
    product_links: Sequence[OrderProductLink],
    composition: WaybillComposition | None = None,
) -> list[dict[str, str]]:
    """Validate per-product prices before freezing the rows in the document snapshot."""
    source = waybill_composition_source(product_links)
    if not source.lines:
        raise ValueError("В выбранном предложении нет товаров для накладной")
    choices = {}
    if composition is not None:
        if composition.source_revision != source.source_revision:
            raise ValueError(
                "Товары предложения изменились. Обновите состав накладной и проверьте строки"
            )
        choices = {line.order_product_line_id: line for line in composition.lines}
        if len(choices) != len(composition.lines) or choices.keys() != {
            line.order_product_line_id for line in source.lines
        }:
            raise ValueError(
                "Состав накладной должен содержать каждую товарную строку выбранного предложения один раз"
            )
    rows: list[dict[str, str]] = []
    for group in source.lines:
        choice = choices.get(group.order_product_line_id)
        components = choice.components if choice else group.components
        if components is None:
            country = (
                choice.whole_country.strip()
                if choice and choice.whole_country is not None
                else group.country
            )
            components = [
                WaybillComponent(
                    title=group.title,
                    country=country,
                    unit="шт.",
                    quantity_per_parent=1,
                    unit_price=group.unit_price,
                )
            ]
        if sum(
            Decimal(part.unit_price) * part.quantity_per_parent for part in components
        ) != Decimal(group.unit_price):
            raise ValueError(
                f"Проверьте цены и количество в составе «{group.title}»: за комплект должно быть {group.unit_price} BYN"
            )
        for component in components:
            quantity = group.quantity * component.quantity_per_parent
            unit_price = Decimal(component.unit_price)
            amount = unit_price * quantity
            rows.append(
                {
                    "line.number": str(len(rows) + 1),
                    "line.title": component.title,
                    "line.kind": "product",
                    "line.country": component.country,
                    "line.unit": component.unit,
                    "line.quantity": str(quantity),
                    "line.unit_price": _money(unit_price),
                    "line.amount": _money(amount),
                    "line.vat_label": "",
                    "line.seats": "",
                    "line.mass": "",
                    "line.note": "—",
                    "line.amount_raw": str(amount),
                    "line.quantity_raw": str(quantity),
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
                "country": _clean(item.get("country")),
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
                "country": _clean(item.get("country")) or _product_country(raw_specs),
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
