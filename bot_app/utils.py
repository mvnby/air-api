import logging
from aiogram import types
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
    from database import is_favorite
    user_id = message_or_callback.from_user.id
    in_fav = await is_favorite(user_id, product['id'])
    
    caption = format_caption(product)
    kb = get_product_keyboard(product['id'], is_admin, in_favorites=in_fav)
    
    target = message_or_callback.answer if isinstance(message_or_callback, types.Message) else message_or_callback.message.answer
    
    # БЕРЕМ ТОЛЬКО ГЛАВНУЮ КАРТИНКУ
    image_url = product.get('main_image')

    if image_url and image_url.startswith('http'):
        try:
            await message_or_callback.bot.send_photo(
                chat_id=message_or_callback.from_user.id,
                photo=image_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logging.error(f"Err photo: {e}")
            await target(text=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await target(text=caption, parse_mode="HTML", reply_markup=kb)
