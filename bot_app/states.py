from aiogram.fsm.state import State, StatesGroup

class ShopState(StatesGroup):
    edit_price = State()
    waiting_for_phone = State()
    waiting_for_search = State()
