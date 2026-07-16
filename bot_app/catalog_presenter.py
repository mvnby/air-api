"""Pure Telegram-side formatting for catalog products."""

from typing import Any

from core.config import settings


def product_url(product: dict[str, Any]) -> str:
    slug = str(product.get("slug") or "").strip()
    base = settings.PUBLIC_SITE_URL.rstrip("/") if settings.PUBLIC_SITE_URL else "https://mvn.by"
    return f"{base}/product/{slug}/" if slug else base


def availability_text(product: dict[str, Any]) -> str:
    vitebsk_qty = int(product.get("vitebsk_qty") or 0)
    minsk_qty = int(product.get("minsk_qty") or 0)
    availability = str(product.get("availability_status") or "").strip().lower()
    if vitebsk_qty > 0:
        return f"Витебск: {vitebsk_qty} шт."
    if minsk_qty > 0:
        return f"Минск: {minsk_qty} шт., обычно 2-3 дня"
    if availability == "in_stock_now":
        return "В наличии"
    if availability == "available_2_3_days":
        return "Доступно 2-3 дня"
    if availability == "check_availability":
        return "Наличие уточнить"
    return "Нет в наличии"


def client_availability_text(product: dict[str, Any]) -> str:
    vitebsk_qty = int(product.get("vitebsk_qty") or 0)
    minsk_qty = int(product.get("minsk_qty") or 0)
    availability = str(product.get("availability_status") or "").strip().lower()
    if vitebsk_qty > 0 or availability == "in_stock_now":
        return "в наличии"
    if minsk_qty > 0 or availability == "available_2_3_days":
        return "в наличии в Минске, срок поставки 2-4 дня"
    return "наличие уточняем"


def format_client_product(product: dict[str, Any]) -> str:
    title = str(product.get("title") or "Кондиционер").strip()
    price = product.get("price")
    price_text = f"{price} руб." if price not in (None, "") else "цену уточним"
    return "\n".join(
        (
            title,
            f"Цена: {price_text}",
            client_availability_text(product),
            product_url(product),
        )
    )
