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

@router.message(F.photo)
async def recognize_requisites_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return
    photo = message.photo[-1]
    await _ask_requisites_file_action(
        message,
        state,
        file_id=photo.file_id,
        filename=f"telegram-photo-{message.message_id}.jpg",
        mime_type="image/jpeg",
        file_size=getattr(photo, "file_size", None),
    )


@router.message(F.document)
async def recognize_requisites_document(message: types.Message, state: FSMContext):
    document = message.document
    if not document:
        return
    mime_type = document.mime_type or ""
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        return
    await _ask_requisites_file_action(
        message,
        state,
        file_id=document.file_id,
        filename=document.file_name or f"telegram-document-{message.message_id}",
        mime_type=mime_type,
        file_size=getattr(document, "file_size", None),
    )


@router.message(StateFilter(None), F.text)
async def recognize_requisites_text(message: types.Message):
    text = message.text or ""
    if not _looks_like_requisites_text(text):
        return
    user_id = message.from_user.id if message.from_user else None
    if not await _is_admin_user(user_id):
        return

    progress = await message.answer("Распознаю реквизиты из текста…")
    await _run_requisites_text_recognition(
        progress,
        text=text,
        telegram_user_id=user_id,
        telegram_chat_id=message.chat.id if message.chat else None,
        telegram_message_id=message.message_id,
    )


@router.callback_query(F.data == "req_file_extract")
async def extract_pending_requisites_file(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Файл не найден. Отправьте его еще раз.", show_alert=True)
        return

    await state.update_data(pending_requisites_file=None)
    await state.set_state(None)
    await callback.answer()
    await callback.message.edit_text("Распознаю реквизиты…")
    await _run_requisites_recognition(
        callback.message,
        file_id=str(pending.get("file_id")),
        filename=str(pending.get("filename") or "telegram-file"),
        mime_type=str(pending.get("mime_type") or "application/octet-stream"),
        file_size=_normalize_file_size(pending.get("file_size")),
        telegram_user_id=callback.from_user.id,
        telegram_chat_id=pending.get("telegram_chat_id") or (callback.message.chat.id if callback.message and callback.message.chat else None),
        telegram_message_id=pending.get("telegram_message_id"),
    )



@router.callback_query(F.data == "req_file_cancel")
async def cancel_pending_requisites_file(callback: CallbackQuery, state: FSMContext):
    await state.update_data(
        pending_requisites_file=None,
        pending_repair_nameplate=None,
        pending_repair_comment=None,
        pending_warranty_nameplate=None,
    )
    await state.set_state(None)
    await callback.message.edit_text("Ок, файл оставил без обработки.")
    await callback.answer()


@router.callback_query(F.data.startswith("ocr_create_") | F.data.startswith("ocr_update_") | F.data.startswith("ocr_cancel_"))
async def confirm_requisites_recognition(callback: CallbackQuery):
    if not await _is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = callback.data or ""
    action = "create" if data.startswith("ocr_create_") else "update" if data.startswith("ocr_update_") else "cancel"
    recognition_id = int(data.rsplit("_", 1)[-1])
    try:
        result = await get_bot_api_gateway().apply_customer_requisites_action(
            telegram_id=callback.from_user.id,
            recognition_id=recognition_id,
            action=action,
        )
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if action == "cancel":
        await callback.message.edit_text("Распознавание отменено.")
        await callback.answer()
        return

    customer = result.customer
    if customer is None:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    customer_id = customer.id
    await callback.message.edit_text(
        f"✅ Клиент {'создан' if action == 'create' else 'обновлен'}: "
        f"<a href=\"{escape(_manager_customer_url(customer_id))}\">{escape(customer.name or str(customer_id))}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()
