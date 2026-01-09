from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database import update_product_price, delete_product
from ..config import ADMIN_ID
from ..states import ShopState

router = Router()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(product_id=callback.data.split("_")[-1])
    await state.set_state(ShopState.edit_price)
    await callback.message.answer("Новая цена (число):")
    await callback.answer()

@router.message(ShopState.edit_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    await update_product_price(int(data['product_id']), int(message.text))
    await message.answer("✅ Цена обновлена.")
    await state.clear()

@router.callback_query(F.data.startswith("del_confirm_"))
async def delete_item(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await delete_product(int(callback.data.split("_")[-1]))
    await callback.message.delete()
    await callback.answer("Удалено")
