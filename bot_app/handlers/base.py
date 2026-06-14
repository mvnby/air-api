from aiogram import Router, types
from aiogram.filters import Command
from core.database import async_session_maker
from services.bot_access_service import BotAccessService
from ..keyboards import get_staff_main_menu

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    async with async_session_maker() as session:
        context = await BotAccessService.get_context(
            session,
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
