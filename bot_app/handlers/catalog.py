from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database import get_all_products, get_products_by_area, search_products
from ..config import ADMIN_ID
from ..keyboards import area_menu
from ..utils import send_product_card
from ..states import ShopState

router = Router()

@router.message(F.text == "📂 Каталог")
async def show_catalog(message: types.Message):
    products = await get_all_products()
    if not products:
        await message.answer("Каталог пуст.")
        return
    
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(f"📦 Товаров в каталоге: {len(products)}")
    
    for product in products[:5]:
        await send_product_card(message, product, is_admin)

@router.message(F.text == "📐 Подбор по площади")
async def start_area(message: types.Message):
    await message.answer("Выберите площадь:", reply_markup=area_menu)

@router.callback_query(F.data.startswith("area_"))
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

@router.message(F.text == "⚡ Инверторные")
async def show_inverters(message: types.Message):
    products = await search_products(is_inverter=True)
    is_admin = message.from_user.id == ADMIN_ID
    
    if not products:
        await message.answer("Инверторные модели не найдены.")
        return

    await message.answer(f"⚡ Найдено инверторов: {len(products)}")
    for product in products:
        await send_product_card(message, product, is_admin)

@router.message(F.text == "🔎 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.waiting_for_search)
    await message.answer("Введите название товара (например, Gree):")

@router.message(ShopState.waiting_for_search)
async def search_process(message: types.Message, state: FSMContext):
    query = message.text
    products = await search_products(query=query)
    is_admin = message.from_user.id == ADMIN_ID
    
    if not products:
        await message.answer(f"Hичего не найдено по запросу '{query}'.")
    else:
        await message.answer(f"🔎 По запросу '{query}' найдено: {len(products)}")
        for product in products:
            await send_product_card(message, product, is_admin)
            
    await state.clear()
