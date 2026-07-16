from aiogram import Router, types
from aiogram.filters import Command

from ..access_runtime import get_bot_access_context
from ..keyboards import get_staff_main_menu

router = Router()

@router.message(Command("start", "menu", "help"))
async def cmd_start(message: types.Message):
    context = await get_bot_access_context(
        message.from_user.id if message.from_user else None,
    )
    if not context.is_staff:
        await message.answer("Этот бот теперь только для сотрудников MVN.")
        return
    name = context.display_name or "коллега"
    await message.answer(
        f"Рабочий бот MVN. Привет, {name}.",
        reply_markup=get_staff_main_menu(context),
    )
