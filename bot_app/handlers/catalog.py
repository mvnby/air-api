import html
import logging

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from core.config import settings
from core.database import async_session_maker
from services.product_service import ProductService
from ..keyboards import (
    area_selection_kb,
    type_selection_kb,
    winter_selection_kb,
    wifi_selection_kb,
    get_search_result_keyboard,
)
from ..utils import send_product_card
from ..states import ShopState

router = Router()
logger = logging.getLogger(__name__)


def _format_price_byn(price: object) -> str:
    try:
        value = int(float(price))
    except (TypeError, ValueError):
        return "—"
    return f"{value:,}".replace(",", " ") + " BYN"


def _format_search_result(product: dict) -> str:
    title = html.escape(str(product.get("title") or "Без названия"))
    area_raw = product.get("area")
    try:
        area_value = int(float(area_raw))
    except (TypeError, ValueError):
        area_value = 0

    power_raw = product.get("power_cooling")
    try:
        power_text = f"{float(power_raw):.1f} кВт"
    except (TypeError, ValueError):
        power_text = "н/д"

    area_text = f"до {area_value} м²" if area_value > 0 else "площадь не указана"
    return (
        f"❄️ <b>{title}</b> ({area_text})\n"
        f"Мощность: {power_text}\n"
        f"Цена: {_format_price_byn(product.get('price'))}"
    )

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
@router.message(Command("search"))
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.waiting_for_search)
    logger.info("BOT_SEARCH_START user_id=%s", message.from_user.id if message.from_user else None)
    await message.answer("Введите бренд и мощность, например: Midea 12")


@router.callback_query(F.data.startswith("search_details_"))
async def search_details(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[-1])
    async with async_session_maker() as session:
        product = await ProductService.get_by_id(session, product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    is_admin = callback.from_user.id == settings.ADMIN_ID
    await send_product_card(callback, product, is_admin)
    await callback.answer()

@router.message(ShopState.waiting_for_search)
async def search_process(message: types.Message, state: FSMContext):
    query = (message.text or "").strip()
    user_id = message.from_user.id if message.from_user else None
    if not query:
        logger.info("BOT_SEARCH_EMPTY_QUERY user_id=%s", user_id)
        await message.answer("Введите бренд и мощность, например: Midea 12")
        return

    async with async_session_maker() as session:
        products = await ProductService.search_products(session, query=query, limit=5)
        sample = [f"{item.get('id')}:{(item.get('title') or '')[:40]}" for item in products[:3]]
        logger.info(
            "BOT_SEARCH_RESULT user_id=%s query=%r found=%s sample=%s",
            user_id,
            query,
            len(products),
            sample,
        )

    if not products:
        await message.answer(
            f"К сожалению, по запросу «{html.escape(query)}» ничего не найдено. "
            "Попробуйте ввести бренд и мощность, например: Midea 12",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"🔎 Нашел {len(products)} вариантов по запросу «{html.escape(query)}».",
            parse_mode="HTML",
        )
        for product in products:
            await message.answer(
                _format_search_result(product),
                parse_mode="HTML",
                reply_markup=get_search_result_keyboard(int(product["id"])),
            )

    await state.clear()
