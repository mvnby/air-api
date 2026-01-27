from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from core.config import settings
from core.database import async_session_maker
from services.product_service import ProductService
from ..keyboards import area_selection_kb, type_selection_kb, winter_selection_kb, wifi_selection_kb
from ..utils import send_product_card
from ..states import ShopState

router = Router()

# ==================== УМНЫЙ ПОДБОР ====================

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
    is_inverter = callback.data == "select_type_inverter"
    await state.update_data(is_inverter=is_inverter)
    await state.set_state(ShopState.select_winter)
    
    type_text = "Премиум (Инвертор)" if is_inverter else "Оптимальный (Стандарт)"
    await callback.message.edit_text(
        f"Выбран тип: {type_text}.\n\n"
        "❄️ Нужен ли обогрев зимой?\n"
        "Если да — выберите минимальную температуру работы:",
        reply_markup=winter_selection_kb
    )
    await callback.answer()

@router.callback_query(ShopState.select_winter, F.data.startswith("select_winter_"))
async def process_winter(callback: CallbackQuery, state: FSMContext):
    winter_val = callback.data.replace("select_winter_", "")
    # winter_val будет "none" или "winter-15", "winter-20", etc.
    winter_tag = None if winter_val == "none" else winter_val
    await state.update_data(winter_tag=winter_tag)
    await state.set_state(ShopState.select_wifi)
    
    winter_text = "Не важно" if winter_val == "none" else f"До {winter_val.replace('winter', '')}°C"
    await callback.message.edit_text(
        f"Обогрев зимой: {winter_text}.\n\n"
        "📶 Нужен ли Wi-Fi модуль для управления со смартфона?",
        reply_markup=wifi_selection_kb
    )
    await callback.answer()

@router.callback_query(ShopState.select_wifi, F.data.startswith("select_wifi_"))
async def process_wifi_and_show_results(callback: CallbackQuery, state: FSMContext):
    wifi_val = callback.data.replace("select_wifi_", "")
    wifi_tag = None if wifi_val == "none" else wifi_val
    
    # Получаем все данные
    data = await state.get_data()
    area = data.get("area")
    is_inverter = data.get("is_inverter")
    winter_tag = data.get("winter_tag")
    
    # Собираем теги для фильтрации
    tag_slugs = []
    if winter_tag:
        tag_slugs.append(winter_tag)
    if wifi_tag:
        tag_slugs.append(wifi_tag)
    
    wifi_text = "Не важно" if wifi_val == "none" else ("Встроенный" if "builtin" in wifi_val else "Опция")
    await callback.message.edit_text(
        f"Wi-Fi: {wifi_text}.\n\n"
        f"🔍 Ищем лучшие модели для площади {area} м²..."
    )
    
    # Получаем товары с фильтрацией по тегам
    async with async_session_maker() as session:
        products = await ProductService.get_curated(
            session, 
            area=area, 
            is_inverter=is_inverter,
            tag_slugs=tag_slugs if tag_slugs else None,
            limit=5  # Максимум 5 результатов
        )
    
    is_admin = callback.from_user.id == settings.ADMIN_ID
    
    if not products:
        await callback.message.answer(
            "К сожалению, по вашим параметрам сейчас ничего не найдено. 😔\n"
            "Попробуйте убрать фильтр по обогреву или Wi-Fi."
        )
    else:
        await callback.message.answer(f"🚀 Вот лучшие предложения для вас ({len(products)} шт.):")
        for product in products:
            await send_product_card(callback, product, is_admin)
            
    await state.clear()
    await callback.answer()

# ==================== ПОИСК ====================

@router.message(F.text == "🔎 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.waiting_for_search)
    await message.answer("Введите название товара (например, Gree или Лофт):")

@router.message(ShopState.waiting_for_search)
async def search_process(message: types.Message, state: FSMContext):
    query = message.text
    
    # Поиск с транслитерацией
    async with async_session_maker() as session:
        products = await ProductService.search(session, query=query, limit=5)
    
    is_admin = message.from_user.id == settings.ADMIN_ID
    
    if not products:
        await message.answer(f"Ничего не найдено по запросу '{query}'.")
    else:
        await message.answer(f"🔎 По запросу '{query}' найдено: {len(products)}")
        for product in products:
            await send_product_card(message, product, is_admin)
            
    await state.clear()
