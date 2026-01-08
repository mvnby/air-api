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
from database import (
    get_all_products, get_products_by_area, 
    update_product_price, delete_product, get_product_by_id
)

load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class ShopState(StatesGroup):
    edit_price = State()
    waiting_for_phone = State()

# --- КЛАВИАТУРЫ ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📂 Каталог"), KeyboardButton(text="📐 Подбор по площади")],
        [KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
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
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_confirm_{product_id}")
        ]
        buttons.append(admin_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ФОРМАТИРОВАНИЕ ---
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
    caption = format_caption(product)
    kb = get_product_keyboard(product['id'], is_admin)
    
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

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Магазин климата ❄️", reply_markup=main_menu)

@dp.message(F.text == "📂 Каталог")
async def show_catalog(message: types.Message):
    products = await get_all_products()
    if not products:
        await message.answer("Каталог пуст.")
        return
    
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(f"📦 Товаров в каталоге: {len(products)}")
    
    for product in products[:5]:
        await send_product_card(message, product, is_admin)

@dp.message(F.text == "📐 Подбор по площади")
async def start_area(message: types.Message):
    await message.answer("Выберите площадь:", reply_markup=area_menu)

@dp.callback_query(F.data.startswith("area_"))
async def process_area(callback: CallbackQuery):
    area_str = callback.data.split("_")[1]
    if not area_str.isdigit(): return
    area = int(area_str)
    
    products = await get_products_by_area(area)
    is_admin = callback.from_user.id == ADMIN_ID
    
    await callback.message.answer(f"🔎 Найдено: {len(products)}")
    for product in products:
        await send_product_card(callback, product, is_admin)
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(product_id=callback.data.split("_")[1])
    await state.set_state(ShopState.waiting_for_phone)
    await callback.message.answer("Введите ваш номер телефона для связи 📱")
    await callback.answer()

@dp.message(ShopState.waiting_for_phone)
async def buy_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product = await get_product_by_id(int(data['product_id']))
    
    if product and ADMIN_ID:
        text = (f"🔔 ЗАКАЗ!\n{message.from_user.full_name}\nTel: {message.text}\n"
                f"Товар: {product['title']} ({product['price']} р)")
        await bot.send_message(ADMIN_ID, text)
    
    await message.answer("✅ Заказ принят!", reply_markup=main_menu)
    await state.clear()

# --- АДМИНКА ---

@dp.callback_query(F.data.startswith("edit_price_"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(product_id=callback.data.split("_")[1])
    await state.set_state(ShopState.edit_price)
    await callback.message.answer("Новая цена (число):")
    await callback.answer()

@dp.message(ShopState.edit_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    await update_product_price(int(data['product_id']), int(message.text))
    await message.answer("✅ Цена обновлена.")
    await state.clear()

@dp.callback_query(F.data.startswith("del_confirm_"))
async def delete_item(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await delete_product(int(callback.data.split("_")[1]))
    await callback.message.delete()
    await callback.answer("Удалено")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())