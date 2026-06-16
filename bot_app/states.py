from aiogram.fsm.state import State, StatesGroup

class ShopState(StatesGroup):
    edit_price = State()
    waiting_for_phone = State()
    waiting_for_search = State()
    waiting_for_quick_order = State()
    waiting_for_selection = State()
    waiting_for_task_report = State()
    waiting_for_order_attachment_order_id = State()
    waiting_for_repair_nameplate_order_id = State()
    waiting_for_repair_context_comment = State()
    select_area = State()
    select_type = State()
    select_winter = State()  # Выбор зимнего обогрева
    select_wifi = State()    # Выбор Wi-Fi
