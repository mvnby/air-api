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

@router.callback_query(F.data == "req_file_attach")
async def choose_order_for_pending_file(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Файл не найден. Отправьте его еще раз.", show_alert=True)
        return

    if context.is_manager:
        response = await get_bot_api_gateway().list_recent_orders(
            telegram_id=callback.from_user.id,
            limit=5,
        )
        orders = [order.model_dump(mode="json") for order in response.items]
    else:
        response = await get_bot_api_gateway().list_my_tasks(
            telegram_id=callback.from_user.id,
            limit=5,
        )
        tasks = [task_to_dict(task) for task in response.items]
        orders = _order_choices_from_tasks(tasks)

    if orders:
        await callback.message.edit_text(
            _format_order_attachment_choices(orders),
            reply_markup=_order_attachment_keyboard(orders),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ShopState.waiting_for_order_attachment_order_id)
        await callback.message.edit_text("Быстрых вариантов не нашел. Введите номер/id заказа сообщением.")
    await callback.answer()


@router.callback_query(F.data == "req_file_attach_manual")
async def enter_order_id_for_pending_file(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Файл не найден. Отправьте его еще раз.", show_alert=True)
        return

    await state.set_state(ShopState.waiting_for_order_attachment_order_id)
    await callback.message.edit_text("Введите номер/id заказа сообщением.")
    await callback.answer()


async def _attach_pending_file_to_order(
    *,
    order_id: int,
    telegram_user_id: int | None,
    can_attach_any: bool,
    state: FSMContext,
) -> dict | None:
    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        return None

    try:
        content = await _download_telegram_file(
            str(pending.get("file_id")),
            expected_size=_normalize_file_size(pending.get("file_size")),
        )
        result = await get_bot_api_gateway().attach_order_file(
            telegram_id=int(telegram_user_id or 0),
            order_id=order_id,
            content=content,
            file_id=str(pending.get("file_id")),
            filename=str(pending.get("filename") or "telegram-file"),
            mime_type=str(pending.get("mime_type") or "application/octet-stream"),
            telegram_chat_id=pending.get("telegram_chat_id"),
            telegram_message_id=pending.get("telegram_message_id"),
        )
        return {"id": result.order_id, "already_attached": result.already_attached}
    except BotApiNotFoundError:
        return {"forbidden": True}
    except Exception as exc:
        return {"error": str(exc)}


@router.callback_query(F.data.startswith("req_file_attach_order_"))
async def attach_pending_file_to_chosen_order(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    order_id = _parse_order_id((callback.data or "").rsplit("_", 1)[-1])
    if not order_id:
        await callback.answer("Не понял номер заказа", show_alert=True)
        return

    result = await _attach_pending_file_to_order(
        order_id=order_id,
        telegram_user_id=callback.from_user.id,
        can_attach_any=context.is_manager,
        state=state,
    )
    if not result:
        await callback.answer("Файл или заказ не найден. Проверьте номер.", show_alert=True)
        return
    if result.get("forbidden"):
        await callback.answer("Этот заказ вам не назначен.", show_alert=True)
        return
    if result.get("error"):
        await callback.answer(f"Не удалось сохранить файл: {result['error']}", show_alert=True)
        return

    await state.update_data(pending_requisites_file=None)
    await state.set_state(None)
    status = "уже был прикреплен" if result.get("already_attached") else "прикреплен"
    await callback.message.edit_text(f"✅ Файл {status} к заказу #{result['id']}.")
    await callback.answer()


@router.message(ShopState.waiting_for_order_attachment_order_id)
async def attach_pending_file_to_typed_order(message: types.Message, state: FSMContext):
    context = await _get_bot_access_context(message.from_user.id if message.from_user else None)
    if not context.is_staff:
        await state.clear()
        return

    order_id = _parse_order_id(message.text)
    if not order_id:
        await message.answer("Введите номер заказа числом, например: 123")
        return

    result = await _attach_pending_file_to_order(
        order_id=order_id,
        telegram_user_id=message.from_user.id if message.from_user else None,
        can_attach_any=context.is_manager,
        state=state,
    )
    if not result:
        await message.answer("Файл или заказ не найден. Отправьте файл еще раз или проверьте номер заказа.")
        return
    if result.get("forbidden"):
        await message.answer("Этот заказ вам не назначен. Проверьте номер заказа или попросите менеджера прикрепить файл.")
        return
    if result.get("error"):
        await message.answer(f"❌ Не удалось сохранить файл: {result['error']}")
        return

    await state.update_data(pending_requisites_file=None)
    await state.set_state(None)
    status = "уже был прикреплен" if result.get("already_attached") else "прикреплен"
    await message.answer(f"✅ Файл {status} к заказу #{result['id']}.")
