from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database import get_curated_products, search_products
from core.config import settings
from ..keyboards import area_selection_kb, type_selection_kb
from ..utils import send_product_card
from ..states import ShopState

router = Router()

@router.message(F.text == "🏆 Умный подбор")
async def start_selection(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.select_area)
    await message.answer(
        "Давайте подберем идеальный кондиционер! 🌬️\n\n"
        "Для начала выберите площадь вашего помещения:",
        reply_markup=area_selection_kb
    )

@router.callback_query(ShopState.select_area, F.data.startswith("select_area_"))
async def process_area(callback: CallbackQuery, state: FSMContext):
    area_val = callback.data.split("_")[-1]
    await state.update_data(area=int(area_val))
    await state.set_state(ShopState.select_type)
    
    await callback.message.edit_text(
        f"Выбрана площадь: до {area_val} м².\n\n"
        "Теперь выберите тип оборудования:\n"
        "🔹 **Оптимальный** — надежные классические модели.\n"
        "🔹 **Премиум** — тихие и экономичные инверторы.",
        reply_markup=type_selection_kb
    )
    await callback.answer()

@router.callback_query(ShopState.select_type, F.data.startswith("select_type_"))
async def process_type(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    area = data.get("area")
    is_inverter = callback.data == "select_type_inverter"
    
    type_text = "Премиум (Инвертор)" if is_inverter else "Оптимальный (Стандарт)"
    await callback.message.edit_text(f"Ищем лучшие модели {type_text} для площади {area} м²...")
    
    products = await get_curated_products(area, is_inverter)
    is_admin = callback.from_user.id == settings.ADMIN_ID
    
    if not products:
        await callback.message.answer("К сожалению, по вашим параметрам сейчас ничего не найдено. Попробуйте изменить поиск.")
    else:
        await callback.message.answer(f"🚀 Вот лучшие предложения для вас:")
        for product in products:
            await send_product_card(callback, product, is_admin)
            
    await state.clear()
    await callback.answer()

@router.message(F.text == "🔎 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.waiting_for_search)
    await message.answer("Введите название товара (например, Gree):")

@router.message(ShopState.waiting_for_search)
async def search_process(message: types.Message, state: FSMContext):
    query = message.text
    products = await search_products(query=query)
    is_admin = message.from_user.id == settings.ADMIN_ID
    
    if not products:
        await message.answer(f"Ничего не найдено по запросу '{query}'.")
    else:
        await message.answer(f"🔎 По запросу '{query}' найдено: {len(products)}")
        for i, product in enumerate(products):
            if i >= 10: break # Safety limit
            await send_product_card(message, product, is_admin)
            
    await state.clear()
