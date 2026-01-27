from aiogram.fsm.state import State, StatesGroup

class ShopState(StatesGroup):
    edit_price = State()
    waiting_for_phone = State()
    waiting_for_search = State()
    select_area = State()
    select_type = State()
    select_winter = State()  # Выбор зимнего обогрева
    select_wifi = State()    # Выбор Wi-Fi

