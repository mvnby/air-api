import logging
import os
from html import escape
from aiogram import types
from .catalog_presenter import availability_text, product_url
from .keyboards import get_product_keyboard


def _availability_badge(product: dict) -> str:
    has_supply_fields = any(
        key in product for key in ("availability_status", "vitebsk_qty", "minsk_qty")
    )
    if not has_supply_fields:
        return ""

    availability = str(product.get("availability_status") or "").strip().lower()
    vitebsk_qty = int(product.get("vitebsk_qty") or 0)
    minsk_qty = int(product.get("minsk_qty") or 0)
    in_stock = (
        vitebsk_qty > 0
        or minsk_qty > 0
        or availability in {"in_stock_now", "available_2_3_days"}
    )
    return "✅ <b>В наличии</b>\n" if in_stock else "⛔ <b>Нет в наличии</b>\n"


def _availability_details(product: dict) -> str:
    if not any(key in product for key in ("availability_status", "vitebsk_qty", "minsk_qty")):
        return ""
    return f"📦 {availability_text(product)}\n"


def format_caption(product):
    # Пытаемся достать характеристики
    specs_str = ""
    # Если categories существует (и это список), выводим красиво
    if product.get('categories') and isinstance(product['categories'], list):
        specs_str += f"📌 {escape(', '.join(str(category) for category in product['categories']))}\n"
    
    return (
        f"❄️ <b>{escape(str(product['title']))}</b>\n"
        f"{_availability_badge(product)}"
        f"{_availability_details(product)}"
        f"💰 <b>{escape(str(product['price']))} руб.</b>\n"
        f"🏠 Площадь: {escape(str(product.get('area', '-')))} м²\n"
        f"{specs_str}"
        f"📝 {escape(str(product.get('description', ''))[:200])}\n"
        f"🔗 {escape(product_url(product))}"
    )

async def send_product_card(message_or_callback, product, is_admin, *, staff_mode=True):
    caption = format_caption(product)
    kb = get_product_keyboard(product['id'], is_admin, product=product, staff_mode=staff_mode)
    
    target = message_or_callback.answer if isinstance(message_or_callback, types.Message) else message_or_callback.message.answer
    
    # БЕРЕМ ТОЛЬКО ГЛАВНУЮ КАРТИНКУ
    image_url = product.get('main_image')

    photo = None
    if image_url:
        if image_url.startswith("http"):
            photo = image_url
        else:
            normalized_path = image_url if image_url.startswith("/") else f"/{image_url}"
            public_api_base = os.getenv("PUBLIC_API_BASE", "https://mvn.by/api/v1").rstrip("/")
            api_prefix = "/api/"
            origin = public_api_base.split(api_prefix, 1)[0] if api_prefix in public_api_base else public_api_base
            photo = f"{origin}{normalized_path}"

    if photo:
        try:
            await message_or_callback.bot.send_photo(
                chat_id=message_or_callback.from_user.id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logging.error("Err photo source=%s error=%s", image_url, e)
            await target(text=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await target(text=caption, parse_mode="HTML", reply_markup=kb)
