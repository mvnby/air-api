from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from core.database import async_session_maker
from services.cart_service import CartService

router = Router()

@router.callback_query(F.data.startswith("buy_"))
async def process_add_to_cart(callback: CallbackQuery):
    """
    Handle 'buy_{product_id}' button. Adds item to cart.
    """
    product_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    async with async_session_maker() as session:
        await CartService.add_product(session, user_id, product_id)
        
    await callback.answer("✅ Товар добавлен в корзину!", show_alert=False)