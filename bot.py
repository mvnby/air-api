import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
# Добавили get_product_by_id в импорт
from database import (
    get_all_products, get_products_by_area, 
    update_product_field, delete_product, get_product_by_id
)

load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- FSM (Состояния разговора) ---
class ShopState(StatesGroup):
    # Состояния для админа
    edit_price = State()
    edit_image = State()
    # Состояние для покупателя
    waiting_for_phone = State()

# --- КЛАВИАТУРЫ ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📂 Каталог"), KeyboardButton(text="📐 Подбор по площади")],
        [KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Меню"
)

area_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="20 м²", callback_data="area_20"), InlineKeyboardButton(text="25 м²", callback_data="area_25")],
        [InlineKeyboardButton(text="35 м²", callback_data="area_35"), InlineKeyboardButton(text="50+ м²", callback_data="area_50")]
    ]
)

def get_product_keyboard(product_id, is_admin=False):
    buttons = [[InlineKeyboardButton(text="🛒 Заказать", callback_data=f"buy_{product_id}")]]
    if is_admin:
        admin_row = [
            InlineKeyboardButton(text="✏️ Цена", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="🖼 Фото", callback_data=f"edit_image_{product_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_confirm_{product_id}")
        ]
        buttons.append(admin_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def format_caption(product):
    return (
        f"❄️ <b>{product['brand']} {product['model']}</b>\n"
        f"💰 <b>{product['price']} руб.</b>\n"
        f"🏠 Площадь: {product['area']} м²\n"
        f"⚡ Инвертор: {'✅' if product['is_inverter'] else '❌'}\n"
    )

async def send_product_card(message_or_callback, product, is_admin):
    caption = format_caption(product)
    kb = get_product_keyboard(product['id'], is_admin)
    
    if isinstance(message_or_callback, types.Message):
        message = message_or_callback
    else:
        message = message_or_callback.message

    if product['image_url'] and product['image_url'].startswith('http'):
        try:
            await message.answer_photo(photo=product['image_url'], caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception:
             await message.answer(text=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text=caption, parse_mode="HTML", reply_markup=kb)


# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать! ❄️", reply_markup=main_menu)

@dp.message(F.text == "📂 Каталог")
async def show_catalog(message: types.Message):
    products = get_all_products()
    if not products:
        await message.answer("В базе пусто.")
        return

    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(f"📦 Товаров: {len(products)}")
    for product in products[:5]:
        await send_product_card(message, product, is_admin)

@dp.message(F.text == "📐 Подбор по площади")
async def start_area_selection(message: types.Message):
    await message.answer("Выберите площадь:", reply_markup=area_menu)

@dp.callback_query(F.data.startswith("area_"))
async def process_area_click(callback: CallbackQuery):
    area = int(callback.data.split("_")[1])
    products = get_products_by_area(area)
    is_admin = callback.from_user.id == ADMIN_ID
    
    await callback.message.answer(f"🔎 Найдено: {len(products)}")
    for product in products:
        await send_product_card(callback, product, is_admin)
    await callback.answer()

# --- ЛОГИКА ЗАКАЗА (ДЛЯ КЛИЕНТА) ---

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_click(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.split("_")[1]
    # Запоминаем, какой товар хотят купить
    await state.update_data(product_id=product_id)
    # Переводим в режим ожидания телефона
    await state.set_state(ShopState.waiting_for_phone)
    
    await callback.message.answer(
        "Для оформления заказа, пожалуйста, напишите ваш <b>номер телефона</b> 📱\n"
        "Например: +375 29 123 45 67",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(ShopState.waiting_for_phone)
async def process_order_phone(message: types.Message, state: FSMContext):
    phone = message.text
    user_data = await state.get_data()
    product_id = user_data.get('product_id')
    
    # Получаем инфо о товаре из базы
    product = get_product_by_id(product_id)
    
    if product:
        # 1. Отправляем уведомление АДМИНУ
        admin_text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n\n"
            f"👤 Клиент: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"📞 Телефон: <code>{phone}</code>\n"
            f"❄️ Товар: {product['brand']} {product['model']}\n"
            f"💰 Цена: {product['price']} руб."
        )
        try:
            if ADMIN_ID:
                await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
            else:
                print(f"Заказ (не отправлен, т.к. нет ADMIN_ID): {admin_text}")
        except Exception as e:
            logging.error(f"Ошибка уведомления админа: {e}")

    # 2. Отвечаем КЛИЕНТУ
    await message.answer("✅ Спасибо! Ваша заявка принята. Менеджер свяжется с вами в ближайшее время.", reply_markup=main_menu)
    await state.clear()


# --- АДМИНКА ---

@dp.callback_query(F.data.startswith("edit_price_"))
async def admin_edit_price_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(product_id=callback.data.split("_")[2])
    await state.set_state(ShopState.edit_price)
    await callback.message.answer("✍️ Введите новую цену:")
    await callback.answer()

@dp.message(ShopState.edit_price)
async def admin_edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Это не число.")
        return
    data = await state.get_data()
    update_product_field(data['product_id'], 'price', int(message.text))
    await message.answer("✅ Цена обновлена.")
    await state.clear()

@dp.callback_query(F.data.startswith("edit_image_"))
async def admin_edit_image_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(product_id=callback.data.split("_")[2])
    await state.set_state(ShopState.edit_image)
    await callback.message.answer("🖼 Пришлите ссылку на фото (или 'нет'):")
    await callback.answer()

@dp.message(ShopState.edit_image)
async def admin_edit_image_finish(message: types.Message, state: FSMContext):
    new_url = message.text if message.text.lower() != 'нет' else ''
    data = await state.get_data()
    update_product_field(data['product_id'], 'image_url', new_url)
    await message.answer("✅ Фото обновлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("del_confirm_"))
async def admin_delete_product(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    delete_product(callback.data.split("_")[2])
    await callback.message.delete()
    await callback.message.answer("🗑 Товар удален.")
    await callback.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())