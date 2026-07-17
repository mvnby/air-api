from io import BytesIO
from html import escape
import os
import re
import secrets

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from api_contracts.bot import BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES
from ..access_runtime import get_bot_access_context
from ..api_gateway import BotApiError, BotApiNotFoundError
from ..api_runtime import get_bot_api_gateway
from ..nameplate_presenter import (
    REPAIR_FIELDS,
    REPAIR_FIELD_LABELS,
    WARRANTY_FIELD_LABELS,
    WARRANTY_UNIT_LABELS,
    WARRANTY_UNIT_TYPES,
)
from ..task_presenter import task_to_dict
from .repair_context import repair_context_keyboard as _repair_context_keyboard
from ..config import bot
from ..states import ShopState

from .admin_common import *

router = Router()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin_user(callback.from_user.id):
        return
    await state.update_data(product_id=callback.data.split("_")[-1])
    await state.set_state(ShopState.edit_price)
    await callback.message.answer("Новая цена (число):")
    await callback.answer()

@router.message(ShopState.edit_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not await _is_admin_user(message.from_user.id if message.from_user else None):
        await state.clear()
        return

    if not message.text.isdigit():
        await message.answer("Цена должна быть числом.")
        return
    data = await state.get_data()

    response = await get_bot_api_gateway().update_product_price(
        telegram_id=message.from_user.id,
        product_id=int(data["product_id"]),
        price=int(message.text),
    )
    updated = response.changed

    if not updated:
        await message.answer("❌ Товар не найден.")
        await state.clear()
        return

    await message.answer("✅ Цена обновлена.")
    await state.clear()

@router.callback_query(F.data.startswith("del_prompt_"))
async def prompt_delete_item(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    product_id = int(callback.data.split("_")[-1])
    token = secrets.token_hex(4)
    await state.update_data(delete_product_confirmation={"product_id": product_id, "token": token})
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"del_confirm_{product_id}_{token}"),
                InlineKeyboardButton(text="Отмена", callback_data="del_cancel"),
            ]
        ]
    )
    await callback.message.answer(
        f"Удалить товар #{product_id}? Действие нельзя отменить.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "del_cancel")
async def cancel_delete_item(callback: CallbackQuery, state: FSMContext):
    await state.update_data(delete_product_confirmation={})
    await callback.message.edit_text("Удаление отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("del_confirm_"))
async def delete_item(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin_user(callback.from_user.id):
        return

    parts = str(callback.data or "").split("_")
    product_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
    token = parts[3] if len(parts) >= 4 else ""
    data = await state.get_data()
    confirmation = data.get("delete_product_confirmation") if isinstance(data, dict) else None
    if (
        not isinstance(confirmation, dict)
        or confirmation.get("product_id") != product_id
        or confirmation.get("token") != token
    ):
        await callback.answer("Подтверждение устарело. Нажмите удалить ещё раз.", show_alert=True)
        return

    try:
        response = await get_bot_api_gateway().delete_product(
            telegram_id=callback.from_user.id,
            product_id=product_id,
        )
        deleted = response.changed
    except BotApiError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if not deleted:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await state.update_data(delete_product_confirmation={})
    await callback.message.delete()
    await callback.answer("Удалено")
