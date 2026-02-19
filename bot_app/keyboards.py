from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏆 Умный подбор"), KeyboardButton(text="🔎 Поиск")],
        [KeyboardButton(text="⭐ Избранное"), KeyboardButton(text="🛒 Корзина")]
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

def get_product_keyboard(product_id, is_admin=False, in_favorites=False):
    fav_text = "💔 Убрать" if in_favorites else "❤️ В избранное"
    buttons = [
        [InlineKeyboardButton(text="🛒 В корзину", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_toggle_{product_id}")]
    ]
    if is_admin:
        admin_row = [
            InlineKeyboardButton(text="✏️ Цена", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_confirm_{product_id}")
        ]
        buttons.append(admin_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_search_result_keyboard(product_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подробнее", callback_data=f"search_details_{product_id}"),
                InlineKeyboardButton(text="В корзину", callback_data=f"buy_{product_id}"),
            ]
        ]
    )
