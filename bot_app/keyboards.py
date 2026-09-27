from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from .access import BotAccessContext
from .catalog_presenter import product_url


def get_staff_main_menu(context: BotAccessContext) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if context.is_manager:
        rows.extend(
            [
                [KeyboardButton(text="⚡ Быстрый заказ"), KeyboardButton(text="🎯 Подбор")],
                [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="📅 Календарь")],
            ]
        )
    if context.is_executor:
        rows.append([KeyboardButton(text="🧰 Мои задачи")])
    if not rows:
        rows.append([KeyboardButton(text="🔎 Поиск")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚡ Быстрый заказ"), KeyboardButton(text="🎯 Подбор")],
        [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="📅 Календарь")],
    ],
    resize_keyboard=True
)

area_selection_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="до 20 м²", callback_data="select_area_20"), 
         InlineKeyboardButton(text="до 25 м²", callback_data="select_area_25")],
        [InlineKeyboardButton(text="до 35 м²", callback_data="select_area_35"), 
         InlineKeyboardButton(text="50+ м²", callback_data="select_area_50")]
    ]
)

type_selection_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Стандарт (ON-OFF)", callback_data="select_type_off")],
        [InlineKeyboardButton(text="💎 Премиум (Инвертор)", callback_data="select_type_inverter")]
    ]
)

# Выбор зимнего обогрева
winter_selection_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="❌ Не важно", callback_data="select_winter_none")],
        [InlineKeyboardButton(text="❄️ До -15°C", callback_data="select_winter_winter-15"),
         InlineKeyboardButton(text="❄️ До -20°C", callback_data="select_winter_winter-20")],
        [InlineKeyboardButton(text="🥶 До -25°C", callback_data="select_winter_winter-25"),
         InlineKeyboardButton(text="🥶 До -30°C", callback_data="select_winter_winter-30")]
    ]
)

# Выбор Wi-Fi
wifi_selection_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="❌ Не важно", callback_data="select_wifi_none")],
        [InlineKeyboardButton(text="📶 Wi-Fi встроенный", callback_data="select_wifi_wifi-builtin")],
        [InlineKeyboardButton(text="📡 Wi-Fi опция", callback_data="select_wifi_wifi-ready")]
    ]
)

def get_product_keyboard(product_id, is_admin=False, in_favorites=False, product=None, staff_mode=True):
    product = product or {}
    url = product_url(product) if product.get("slug") else None
    if staff_mode:
        buttons = []
        if url:
            buttons.append([InlineKeyboardButton(text="Открыть на сайте", url=url)])
            buttons.append(
                [InlineKeyboardButton(text="Текст клиенту", callback_data=f"product_client_text_{product_id}")]
            )
        buttons.append([InlineKeyboardButton(text="Подробнее", callback_data=f"search_details_{product_id}")])
        if is_admin:
            buttons.append(
                [
                    InlineKeyboardButton(text="✏️ Цена", callback_data=f"edit_price_{product_id}"),
                    InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_prompt_{product_id}"),
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    fav_text = "💔 Убрать" if in_favorites else "❤️ В избранное"
    buttons = [
        [InlineKeyboardButton(text="🛒 В корзину", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_toggle_{product_id}")]
    ]
    if is_admin:
        admin_row = [
            InlineKeyboardButton(text="✏️ Цена", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_prompt_{product_id}")
        ]
        buttons.append(admin_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_search_result_keyboard(product_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подробнее", callback_data=f"search_details_{product_id}"),
            ]
        ]
    )


def quick_order_confirm_keyboard(draft_id: str | None = None, version: int | None = None) -> InlineKeyboardMarkup:
    suffix = f":{draft_id}:{version}" if draft_id and version is not None else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Создать заказ" if suffix else "Создать", callback_data=f"qo_create{suffix}" if suffix else "quick_order_create"),
                InlineKeyboardButton(text="Исправить", callback_data=f"qo_edit{suffix}" if suffix else "quick_order_retry"),
            ],
            [InlineKeyboardButton(text="Сценарий", callback_data=f"qo_scenarios{suffix}" if suffix else "quick_order_retry"),
             InlineKeyboardButton(text="Адрес", callback_data=f"qo_address{suffix}" if suffix else "quick_order_retry"),
             InlineKeyboardButton(text="Дата", callback_data=f"qo_date{suffix}" if suffix else "quick_order_retry")],
            [InlineKeyboardButton(text="Клиент", callback_data=f"qo_client{suffix}" if suffix else "quick_order_retry"),
             InlineKeyboardButton(text="Другие данные", callback_data=f"qo_other{suffix}" if suffix else "quick_order_retry")],
            [InlineKeyboardButton(text="Отмена", callback_data=f"qo_cancel{suffix}" if suffix else "quick_order_cancel")],
        ]
    )


def quick_order_scenario_keyboard(draft_id: str, version: int, scenarios: list) -> InlineKeyboardMarkup:
    rows = []
    for scenario in scenarios:
        code = scenario.service_type or "works"
        rows.append([InlineKeyboardButton(
            text=scenario.label,
            callback_data=f"qo_select:{draft_id}:{version}:{code}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def selection_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Текст клиенту", callback_data="selection_client_text")],
        ]
    )


def task_actions_keyboard(tasks: list[dict]) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks[:5]:
        if task.get("kind") != "stage":
            continue
        stage_id = task.get("id")
        rows.append(
            [
                InlineKeyboardButton(text=f"Принял #{task['order_id']}", callback_data=f"task_accept_{stage_id}"),
                InlineKeyboardButton(text=f"Выполнено #{task['order_id']}", callback_data=f"task_done_{stage_id}"),
            ]
        )
        rows.append([InlineKeyboardButton(text=f"Отчет #{task['order_id']}", callback_data=f"task_report_{stage_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
