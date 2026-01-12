from aiogram import Router, types, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from core.config import settings
from core.database import async_session_maker
from core.logger import logger
from services.product_service import ProductService
from services.order_service import OrderService
from ..config import bot
from ..states import ShopState
from ..keyboards import main_menu

router = Router()

@router.callback_query(F.data.startswith("buy_"))
async def buy_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(product_id=callback.data.split("_")[-1])
    await state.set_state(ShopState.waiting_for_phone)
    await callback.message.answer("Введите ваш номер телефона для связи 📱\n(или отправьте любой текст, если хотите оставить только Telegram контакт)")
    await callback.answer()

@router.message(ShopState.waiting_for_phone)
async def buy_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_id = int(data['product_id'])
    
    user = message.from_user
    
    # Use new Service Layer with session
    async with async_session_maker() as session:
        product = await ProductService.get_by_id(session, product_id)
        order = await OrderService.create_order(
            session,
            user_id=user.id,
            product_id=product_id,
            username=user.username,
            full_name=user.full_name,
            phone=message.text
        )

    if product and settings.admin_list:
        text = (f"🔔 НОВЫЙ ЗАКАЗ #{order.id}!\n"
                f"👤 {user.full_name} (@{user.username})\n"
                f"📱 Tel: {message.text}\n"
                f"❄️ Товар: {product['title']} ({product['price']} р)")
        
        for admin_id in settings.admin_list:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    await message.answer("✅ Заказ принят!", reply_markup=main_menu)
    await state.clear()
