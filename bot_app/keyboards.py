from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📂 Каталог"), KeyboardButton(text="📐 Подбор по площади")],
        [KeyboardButton(text="⚡ Инверторные"), KeyboardButton(text="🔎 Поиск")],
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
