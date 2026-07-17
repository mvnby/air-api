"""Pure Telegram formatting for product selections returned by the API."""

from html import escape
import re
from typing import Any

from .catalog_presenter import client_availability_text, product_url


def _area_label(area: dict[str, Any]) -> str:
    label = str(area.get("label") or f"{area.get('area')} м²")
    quantity = int(area.get("quantity") or 1)
    return f"{label}, {quantity} шт." if quantity > 1 else label


def _price(product: dict[str, Any]) -> int | None:
    try:
        value = product.get("price")
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _price_text(product: dict[str, Any], quantity: int = 1) -> str:
    price = _price(product)
    if price is None:
        return "цену уточним"
    if quantity <= 1:
        return f"{price} руб."
    return f"{price} руб. x {quantity} шт. = {price * quantity} руб."


def _availability(product: dict[str, Any]) -> str:
    vitebsk_qty = int(product.get("vitebsk_qty") or 0)
    minsk_qty = int(product.get("minsk_qty") or 0)
    status = str(product.get("availability_status") or "").lower()
    if vitebsk_qty > 0:
        return f"Витебск: {vitebsk_qty} шт."
    if minsk_qty > 0:
        return f"Минск: {minsk_qty} шт., обычно 2-3 дня"
    return {"in_stock_now": "В наличии", "available_2_3_days": "Доступно 2-3 дня", "check_availability": "Наличие уточнить"}.get(status, "Нет в наличии")


def _tier_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    known = {"бюджетнее": "Бюджетный вариант", "оптимально": "Оптимальный вариант", "премиум": "Премиальный вариант", "on-off": "ON-OFF вариант"}
    if normalized in known:
        return known[normalized]
    label = str(value or "Вариант").strip()
    return label if label.lower().endswith("вариант") else f"{label} вариант"


def _spec_number(value: Any, *, nominal_from_range: bool = False) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if number > 0 else None
    text = str(value).replace(",", ".")
    matches = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not matches:
        return None
    if nominal_from_range and len(matches) >= 3 and "/" in text:
        return matches[1]
    return max(matches)


def _decimal(value: float) -> str:
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _characteristics(product: dict[str, Any]) -> str:
    specs = product.get("specs") if isinstance(product.get("specs"), dict) else {}
    power = _spec_number(product.get("power_cooling"))
    if power is None:
        for key in (
            "capacity_cooling_kw",
            "Мощность охлаждения",
            "Мощность охлаждения, кВт",
            "Охлаждение, кВт",
        ):
            power = _spec_number(specs.get(key), nominal_from_range=True)
            if power is not None:
                break
    area = _spec_number(product.get("area"))
    if area is None:
        for key in (
            "area_m2",
            "Обслуживаемая площадь",
            "Обслуживаемая площадь до",
            "Рекомендуемая максимальная площадь помещения",
        ):
            area = _spec_number(specs.get(key))
            if area is not None:
                break
    parts = []
    if power is not None:
        parts.append(f"мощность {_decimal(power)} кВт")
    if area is not None:
        parts.append(f"на {_decimal(area)} м²")
    return f" {', '.join(parts)}" if parts else ""


def _client_line(product: dict[str, Any], quantity: int) -> str:
    return (
        f"- кондиционер {str(product.get('title') or 'Кондиционер').strip()}"
        f"{_characteristics(product)}\n"
        f"  {_price_text(product, quantity)}\n"
        f"  {client_availability_text(product)}\n"
        f"  {product_url(product)}"
    )


def format_selection(selection: dict[str, Any]) -> str:
    areas = selection.get("areas") or []
    if not areas:
        return escape(str(selection.get("message") or "Ничего не подобрал."))
    lines = ["<b>Подбор кондиционеров для клиента</b>"]
    if selection.get("compressor_mode") == "inverter_only":
        lines.append("Режим: только инверторы")
    elif selection.get("compressor_mode") == "onoff_only":
        reason = f" ({selection.get('mode_reason')})" if selection.get("mode_reason") else ""
        lines.append(f"Режим: только ON-OFF{escape(reason)}")
    for area in areas:
        quantity = int(area.get("quantity") or 1)
        lines.extend(["", f"<b>{escape(_area_label(area))}</b>"])
        for tier in area.get("tiers", []):
            products = tier.get("products") or []
            label = escape(str(tier.get("label") or "Вариант"))
            if not products:
                lines.append(f"{label}: нет подходящих моделей")
                continue
            product = products[0]
            lines.append(f"{label}: {escape(str(product.get('title') or 'Товар'))} - {escape(_price_text(product, quantity))}\n{escape(_availability(product))}\n{escape(product_url(product))}")
    return "\n".join(lines)


def format_selection_rich_html(selection: dict[str, Any]) -> str:
    areas = selection.get("areas") or []
    if not areas:
        return f"<h3>Подбор кондиционеров</h3><p>{escape(str(selection.get('message') or 'Ничего не подобрал.'))}</p>"
    blocks = ["<h3>Подбор кондиционеров для клиента</h3>"]
    for area in areas:
        quantity = int(area.get("quantity") or 1)
        blocks.append(f"<h4>{escape(_area_label(area))}</h4>")
        for tier in area.get("tiers", []):
            products = tier.get("products") or []
            label = escape(str(tier.get("label") or "Вариант"))
            if not products:
                blocks.append(f"<p><b>{label}:</b> нет подходящих моделей</p>")
                continue
            product = products[0]
            blocks.append(f"<p><b>{label}:</b> {escape(str(product.get('title') or 'Товар'))}<br/><b>Цена:</b> {escape(_price_text(product, quantity))}<br/><b>Наличие:</b> {escape(_availability(product))}<br/><a href=\"{escape(product_url(product))}\">Открыть товар на сайте</a></p>")
    return "".join(blocks)


def format_client_selection(selection: dict[str, Any]) -> str:
    areas = selection.get("areas") or []
    if not areas:
        return str(selection.get("message") or "Пока не получилось подобрать варианты.")
    is_kit = len(areas) > 1 or any(int(area.get("quantity") or 1) > 1 for area in areas)
    if not is_kit:
        lines = ["Подобрал варианты кондиционеров:"]
        for tier in areas[0].get("tiers", []):
            products = tier.get("products") or []
            if products:
                lines.extend(["", f"{_tier_label(tier.get('label'))}:\n{_client_line(products[0], 1)}"])
        return "\n".join(lines) if len(lines) > 1 else "Пока не получилось подобрать варианты из наличия."
    keys = list(dict.fromkeys(str(tier.get("key") or tier.get("label") or "") for area in areas for tier in area.get("tiers", []) if tier.get("products")))
    lines = ["Подобрал варианты кондиционеров комплектом:"]
    for key in keys:
        items, label, total, complete = [], "", 0, True
        for area in areas:
            tier = next((item for item in area.get("tiers", []) if str(item.get("key") or item.get("label") or "") == key), None)
            products = (tier or {}).get("products") or []
            if not products:
                continue
            quantity = int(area.get("quantity") or 1)
            label = label or str((tier or {}).get("label") or "Вариант")
            price = _price(products[0])
            complete = complete and price is not None
            total += (price or 0) * quantity
            items.append(_client_line(products[0], quantity))
        if items:
            lines.extend(["", f"{_tier_label(label)}:", *items, f"Итого по варианту: {total} руб." if complete else "Итого по варианту: цену уточним"])
    return "\n".join(lines)
