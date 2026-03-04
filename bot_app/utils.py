import logging
import os
from pathlib import Path
from aiogram import types
from aiogram.types import FSInputFile
from core.database import async_session_maker
from services.favorite_service import FavoriteService
from .keyboards import get_product_keyboard

def format_caption(product):
    # Пытаемся достать характеристики
    specs_str = ""
    # Если categories существует (и это список), выводим красиво
    if product.get('categories') and isinstance(product['categories'], list):
        specs_str += f"📌 {', '.join(product['categories'])}\n"
    
    return (
        f"❄️ <b>{product['title']}</b>\n"
        f"💰 <b>{product['price']} руб.</b>\n"
        f"🏠 Площадь: {product.get('area', '-')} м²\n"
        f"{specs_str}"
        f"📝 {product.get('description', '')[:200]}"
    )

async def send_product_card(message_or_callback, product, is_admin):
    user_id = message_or_callback.from_user.id
    
    # Use new Service Layer
    async with async_session_maker() as session:
        in_fav = await FavoriteService.is_favorite(session, user_id, product['id'])
    
    caption = format_caption(product)
    kb = get_product_keyboard(product['id'], is_admin, in_favorites=in_fav)
    
    target = message_or_callback.answer if isinstance(message_or_callback, types.Message) else message_or_callback.message.answer
    
    # БЕРЕМ ТОЛЬКО ГЛАВНУЮ КАРТИНКУ
    image_url = product.get('main_image')

    photo = None
    if image_url:
        if image_url.startswith("http"):
            photo = image_url
        else:
            normalized_path = image_url if image_url.startswith("/") else f"/{image_url}"
            local_path = Path(normalized_path.lstrip("/"))
            if local_path.exists() and local_path.is_file():
                photo = FSInputFile(str(local_path))
            else:
                logging.warning("Bot image local file not found: %s", local_path)
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
