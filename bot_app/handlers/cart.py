from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.database import async_session_maker
from core.config import settings
from services.cart_service import CartService
from bot_app.states import ShopState
from bot_app.config import bot
from bot_app.keyboards import main_menu

router = Router()

@router.message(F.text == "🛒 Корзина")
@router.message(Command("cart"))
async def show_cart(message: types.Message):
    user_id = message.from_user.id
    
    async with async_session_maker() as session:
        summary = await CartService.get_cart_summary(session, user_id)
    
    if summary["is_empty"]:
        await message.answer("🛒 Ваша корзина пуста.\nПерейдите в каталог, чтобы выбрать товары.")
        return

    # Формируем текст
    text_lines = ["<b>🛒 Ваша Корзина:</b>\n"]
    for item in summary["items"]:
        text_lines.append(f"▫️ {item['title']}")
        text_lines.append(f"   {item['quantity']} шт. x {item['price']} р. = <b>{item['line_sum']} р.</b>")
    
    text_lines.append(f"\n<b>💰 ИТОГО: {summary['total_price']} руб.</b>")
    
    # Кнопки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="cart_checkout")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart_clear")]
    ])
    
    await message.answer("\n".join(text_lines), reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "cart_clear")
async def clear_cart_handler(callback: types.CallbackQuery):
    async with async_session_maker() as session:
        await CartService.clear_cart(session, callback.from_user.id)
    await callback.message.edit_text("🗑 Корзина очищена.")
    await callback.answer()

@router.callback_query(F.data == "cart_checkout")
async def start_checkout(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopState.waiting_for_phone)
    await callback.message.answer(
        "📞 Пожалуйста, введите ваш номер телефона для подтверждения заказа:",
        reply_markup=types.ReplyKeyboardRemove() # Убираем главное меню временно
    )
    await callback.answer()

@router.message(ShopState.waiting_for_phone)
async def finish_checkout(message: types.Message, state: FSMContext):
    phone = message.text
    user = message.from_user
    
    async with async_session_maker() as session:
        try:
            order = await CartService.checkout(
                session, 
                user_id=user.id, 
                contact_info=phone,
                username=user.username,
                full_name=user.full_name
            )
            
            # Уведомление админам
            if settings.admin_list:
                admin_text = (
                    f"🔔 <b>НОВЫЙ ЗАКАЗ #{order.id}</b>\n"
                    f"👤 {user.full_name} (@{user.username})\n"
                    f"📱 {phone}\n"
                    f"💰 Сумма: {order.total_amount} руб."
                )
                for admin_id in settings.admin_list:
                    try:
                        await bot.send_message(admin_id, admin_text, parse_mode="HTML")
                    except Exception:
                        pass  # Ignore notification failures
            
            await message.answer(f"✅ <b>Заказ #{order.id} успешно оформлен!</b>\nМы свяжемся с вами в ближайшее время.", reply_markup=main_menu, parse_mode="HTML")
            
        except ValueError:
            await message.answer("❌ Корзина пуста.", reply_markup=main_menu)
        except Exception as e:
            await message.answer("❌ Произошла ошибка при оформлении. Попробуйте позже.", reply_markup=main_menu)
            print(f"Checkout error: {e}")
            
    await state.clear()