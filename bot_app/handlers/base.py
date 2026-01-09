from aiogram import Router, types
from aiogram.filters import Command
from ..keyboards import main_menu

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Магазин климата ❄️", reply_markup=main_menu)
