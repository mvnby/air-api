from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from core.config import settings
from core.database import async_session_maker
from services.product_service import ProductService
from ..states import ShopState

router = Router()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext):
    if not settings.is_admin_user(callback.from_user.id): return
    await state.update_data(product_id=callback.data.split("_")[-1])
    await state.set_state(ShopState.edit_price)
    await callback.message.answer("Новая цена (число):")
    await callback.answer()

@router.message(ShopState.edit_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Цена должна быть числом.")
        return
    data = await state.get_data()
    
    async with async_session_maker() as session:
        updated = await ProductService.update_price(session, int(data["product_id"]), int(message.text))

    if not updated:
        await message.answer("❌ Товар не найден.")
        await state.clear()
        return

    await message.answer("✅ Цена обновлена.")
    await state.clear()

@router.callback_query(F.data.startswith("del_confirm_"))
async def delete_item(callback: CallbackQuery):
    if not settings.is_admin_user(callback.from_user.id): return
    
    async with async_session_maker() as session:
        try:
            deleted = await ProductService.delete(session, int(callback.data.split("_")[-1]))
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    if not deleted:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.message.delete()
    await callback.answer("Удалено")
