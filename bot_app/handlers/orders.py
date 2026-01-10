from aiogram import Router, types, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database import get_product_by_id, create_order
from core.config import settings
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
    product = await get_product_by_id(product_id)
    
    # Create Order in DB
    user = message.from_user
    order = await create_order(
        user_id=user.id,
        product_id=product_id,
        username=user.username,
        full_name=user.full_name,
        phone=message.text
    )

    if product and settings.ADMIN_ID:
        text = (f"🔔 НОВЫЙ ЗАКАЗ #{order.id}!\n"
                f"👤 {user.full_name} (@{user.username})\n"
                f"📱 Tel: {message.text}\n"
                f"❄️ Товар: {product['title']} ({product['price']} р)")
        await bot.send_message(settings.ADMIN_ID, text)
    
    await message.answer("✅ Заказ принят!", reply_markup=main_menu)
    await state.clear()
