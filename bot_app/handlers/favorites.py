from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from core.config import settings
from core.database import async_session_maker
from services.favorite_service import FavoriteService
from ..utils import send_product_card, format_caption
from ..keyboards import get_product_keyboard

router = Router()

@router.message(F.text == "⭐ Избранное")
async def show_favorites(message: types.Message):
    user_id = message.from_user.id
    
    async with async_session_maker() as session:
        favs = await FavoriteService.get_favorites(session, user_id)
    
    if not favs:
        await message.answer("У вас пока нет избранных товаров.")
        return
        
    await message.answer(f"⭐ Ваши избранные товары ({len(favs)}):")
    is_admin = user_id == settings.ADMIN_ID
    for product in favs:
        await send_product_card(message, product, is_admin)

@router.callback_query(F.data.startswith("fav_toggle_"))
async def process_fav_toggle(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    async with async_session_maker() as session:
        is_added = await FavoriteService.toggle(session, user_id, product_id)
    
    status_msg = "Добавлено в избранное! ❤️" if is_added else "Удалено из избранного. 💔"
    
    # Update the keyboard on the existing message
    is_admin = user_id == settings.ADMIN_ID
    new_kb = get_product_keyboard(product_id, is_admin, in_favorites=is_added)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        pass # Message might be old or unchanged
        
    await callback.answer(status_msg)
