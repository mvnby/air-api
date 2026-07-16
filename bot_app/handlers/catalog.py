import html
import logging
import re

from aiogram import Router, types, F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, StateFilter
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from core.database import async_session_maker
from services.bot_product_selection_service import BotProductSelectionService
from services.product_service import ProductService
from ..access_runtime import get_bot_access_context
from ..keyboards import (
    area_selection_kb,
    get_staff_main_menu,
    type_selection_kb,
    winter_selection_kb,
    wifi_selection_kb,
)
from ..utils import send_product_card
from ..states import ShopState

router = Router()
logger = logging.getLogger(__name__)


async def _get_access_context(user_id: int | None):
    return await get_bot_access_context(user_id)


async def _is_staff_user(user_id: int | None) -> bool:
    context = await _get_access_context(user_id)
    return context.is_staff


async def _is_manager_user(user_id: int | None) -> bool:
    context = await _get_access_context(user_id)
    return context.is_staff and context.is_manager


async def _answer_with_staff_menu(message: types.Message, user_id: int | None) -> None:
    context = await _get_access_context(user_id)
    if context.is_staff:
        await message.answer("Можно продолжить работу из меню.", reply_markup=get_staff_main_menu(context))


def _is_inline_search_query(text: str) -> bool:
    if not text:
        return False
    # 1..3 tokens, each token contains only latin letters/digits.
    return bool(re.fullmatch(r"[A-Za-z0-9]+(?:\s+[A-Za-z0-9]+){0,2}", text.strip()))


def _is_in_stock_product(product: dict) -> bool:
    availability = str(product.get("availability_status") or "").strip().lower()
    vitebsk_qty = int(product.get("vitebsk_qty") or 0)
    minsk_qty = int(product.get("minsk_qty") or 0)
    if vitebsk_qty > 0 or minsk_qty > 0:
        return True
    return availability in {"in_stock_now", "available_2_3_days"}


def _choose_search_products(products: list[dict]) -> tuple[list[dict], str | None]:
    in_stock = [p for p in products if _is_in_stock_product(p)]
    if in_stock:
        return in_stock, None
    if products:
        return (
            products,
            "⚠️ По вашему запросу сейчас нет товаров в наличии на складах.\n"
            "Показываю доступные модели, но лучше уточнить сроки поставки у менеджера.",
        )
    return [], None


async def _render_search_results(message: types.Message, query: str, products: list[dict]) -> None:
    selected_products, warning_text = _choose_search_products(products)
    if not selected_products:
        await message.answer(
            f"К сожалению, по запросу «{html.escape(query)}» ничего не найдено. "
            "Попробуйте ввести бренд и мощность, например: Midea 12",
            parse_mode="HTML",
        )
        return

    if warning_text:
        await message.answer(warning_text)

    await message.answer(
        f"🔎 Нашел {len(selected_products)} вариантов по запросу «{html.escape(query)}».",
        parse_mode="HTML",
    )
    context = await _get_access_context(message.from_user.id if message.from_user else None)
    is_admin = context.is_staff and context.is_manager
    for product in selected_products:
        await send_product_card(message, product, is_admin)


# ==================== УМНЫЙ ПОДБОР ====================

@router.message(F.text == "🏆 Умный подбор")
async def start_selection(message: types.Message, state: FSMContext):
    if not await _is_manager_user(message.from_user.id if message.from_user else None):
        await message.answer("Подбор доступен сотрудникам MVN.")
        return
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
    context = await _get_access_context(callback.from_user.id)
    async with async_session_maker() as session:
        products = await ProductService.get_curated(
            session, 
            area=area, 
            is_inverter=is_inverter,
            tag_slugs=tag_slugs if tag_slugs else None,
            limit=5  # Максимум 5 результатов
        )
        is_admin = context.is_staff and context.is_manager
    
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
    await _answer_with_staff_menu(callback.message, callback.from_user.id)
    await callback.answer()

# ==================== ПОИСК ====================

@router.message(F.text == "🔎 Поиск")
@router.message(Command("search"))
async def search_start(message: types.Message, state: FSMContext):
    if not await _is_staff_user(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот теперь только для сотрудников MVN.")
        return
    await state.set_state(ShopState.waiting_for_search)
    logger.info("BOT_SEARCH_START user_id=%s", message.from_user.id if message.from_user else None)
    await message.answer("Введите бренд и мощность, например: Midea 12")


@router.callback_query(F.data.startswith("search_details_"))
async def search_details(callback: CallbackQuery):
    if not await _is_staff_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    product_id = int(callback.data.split("_")[-1])
    context = await _get_access_context(callback.from_user.id)
    async with async_session_maker() as session:
        product = await ProductService.get_by_id(session, product_id)
        is_admin = context.is_staff and context.is_manager

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await send_product_card(callback, product, is_admin)
    await callback.answer()


@router.callback_query(F.data.startswith("product_client_text_"))
async def product_client_text(callback: CallbackQuery):
    if not await _is_staff_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    product_id = int((callback.data or "").split("_")[-1])
    async with async_session_maker() as session:
        product = await ProductService.get_by_id(session, product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.message.answer(BotProductSelectionService.format_client_product(product))
    await callback.answer("Можно переслать клиенту")


@router.message(ShopState.waiting_for_search)
async def search_process(message: types.Message, state: FSMContext):
    if not await _is_staff_user(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот теперь только для сотрудников MVN.")
        await state.clear()
        return
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

    await _render_search_results(message, query, products)

    await state.clear()
    await _answer_with_staff_menu(message, user_id)


@router.message(StateFilter(None), F.text)
async def auto_search_process(message: types.Message):
    query = (message.text or "").strip()
    user_id = message.from_user.id if message.from_user else None
    if not _is_inline_search_query(query):
        raise SkipHandler()
    if not await _is_staff_user(user_id):
        return

    async with async_session_maker() as session:
        products = await ProductService.search_products(session, query=query, limit=5)
        sample = [f"{item.get('id')}:{(item.get('title') or '')[:40]}" for item in products[:3]]
        logger.info(
            "BOT_AUTO_SEARCH_RESULT user_id=%s query=%r found=%s sample=%s",
            user_id,
            query,
            len(products),
            sample,
        )
    await _render_search_results(message, query, products)
