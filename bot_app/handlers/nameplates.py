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

@router.callback_query(F.data == "repair_nameplate_start")
async def choose_order_for_repair_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return
    if not str(pending.get("mime_type") or "").startswith("image/"):
        await callback.answer("Шильдик распознаем только по фото.", show_alert=True)
        return

    response = await get_bot_api_gateway().list_repair_nameplate_orders(
        telegram_id=callback.from_user.id,
        limit=5,
    )
    orders = [order.model_dump(mode="json") for order in response.items]

    if orders:
        await callback.message.edit_text(
            _format_repair_nameplate_order_choices(orders),
            reply_markup=_repair_nameplate_order_keyboard(orders),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ShopState.waiting_for_repair_nameplate_order_id)
        await callback.message.edit_text(
            "Быстрых активных ремонтных заказов не нашел. Введите номер/id заказа сообщением."
        )
    await callback.answer()


@router.callback_query(F.data == "repair_nameplate_manual")
async def enter_order_id_for_repair_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return

    await state.set_state(ShopState.waiting_for_repair_nameplate_order_id)
    await callback.message.edit_text("Введите номер/id ремонтного заказа сообщением.")
    await callback.answer()


async def _run_repair_nameplate_recognition_for_order(
    progress_message: types.Message,
    *,
    order_id: int,
    telegram_user_id: int | None,
    can_attach_any: bool,
    state: FSMContext,
):
    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await progress_message.edit_text("Фото не найдено. Отправьте его еще раз.")
        return

    try:
        content = await _download_telegram_file(
            str(pending.get("file_id")),
            expected_size=_normalize_file_size(pending.get("file_size")),
        )
        response = await get_bot_api_gateway().recognize_repair_nameplate(
            telegram_id=int(telegram_user_id or 0),
            order_id=order_id,
            content=content,
            filename=str(pending.get("filename") or "telegram-nameplate.jpg"),
            mime_type=str(pending.get("mime_type") or "image/jpeg"),
        )
        recognized = response.model_dump(mode="json")
        merge_preview = recognized.get("merge_preview") or {}
    except BotApiNotFoundError:
        await progress_message.edit_text(
            "Этот заказ не найден среди активных ремонтных заказов или не назначен вам."
        )
        return
    except Exception as exc:
        await progress_message.edit_text(f"❌ Не удалось распознать шильдик: {escape(str(exc))}")
        return

    draft = {
        "order_id": order_id,
        "file": pending,
        "raw_text": recognized.get("raw_text") or "",
        "extracted": recognized.get("extracted") or {},
        "validation_flags": recognized.get("validation_flags") or {},
        "merge_preview": merge_preview or {"applied": {}, "conflicts": {}, "skipped": {}},
    }
    await state.update_data(pending_repair_nameplate=draft)
    await state.set_state(None)
    await progress_message.edit_text(
        _repair_nameplate_preview_text(draft),
        reply_markup=_repair_nameplate_preview_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("repair_nameplate_order_"))
async def recognize_repair_nameplate_for_chosen_order(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    order_id = _parse_order_id((callback.data or "").rsplit("_", 1)[-1])
    if not order_id:
        await callback.answer("Не понял номер заказа", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("Распознаю шильдик…")
    await _run_repair_nameplate_recognition_for_order(
        callback.message,
        order_id=order_id,
        telegram_user_id=callback.from_user.id,
        can_attach_any=context.is_manager,
        state=state,
    )


@router.message(ShopState.waiting_for_repair_nameplate_order_id)
async def recognize_repair_nameplate_for_typed_order(message: types.Message, state: FSMContext):
    context = await _get_bot_access_context(message.from_user.id if message.from_user else None)
    if not context.is_staff:
        await state.clear()
        return

    order_id = _parse_order_id(message.text)
    if not order_id:
        await message.answer("Введите номер ремонтного заказа числом, например: 123")
        return

    progress = await message.answer("Распознаю шильдик…")
    await _run_repair_nameplate_recognition_for_order(
        progress,
        order_id=order_id,
        telegram_user_id=message.from_user.id if message.from_user else None,
        can_attach_any=context.is_manager,
        state=state,
    )


@router.callback_query(F.data == "repair_nameplate_confirm")
async def confirm_repair_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    draft = data.get("pending_repair_nameplate") or {}
    if not isinstance(draft, dict) or not draft.get("order_id"):
        await callback.answer("Черновик не найден. Отправьте фото еще раз.", show_alert=True)
        return
    pending_file = draft.get("file") if isinstance(draft.get("file"), dict) else {}
    if not pending_file or not pending_file.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return

    try:
        file_content = await _download_telegram_file(
            str(pending_file.get("file_id")),
            expected_size=_normalize_file_size(pending_file.get("file_size")),
        )
        response = await get_bot_api_gateway().apply_repair_nameplate(
                telegram_id=callback.from_user.id,
                order_id=int(draft["order_id"]),
                content=file_content,
                extracted=draft.get("extracted") or {},
                raw_text=str(draft.get("raw_text") or ""),
                validation_flags=draft.get("validation_flags") or {},
                file_id=str(pending_file.get("file_id")),
                filename=str(pending_file.get("filename") or "telegram-nameplate.jpg"),
                mime_type=str(pending_file.get("mime_type") or "image/jpeg"),
                telegram_chat_id=pending_file.get("telegram_chat_id"),
                telegram_message_id=pending_file.get("telegram_message_id"),
            )
        result = response.result
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if not result:
        await callback.answer("Заказ не найден или недоступен.", show_alert=True)
        return

    await state.update_data(
        pending_repair_nameplate=None,
        pending_requisites_file=None,
        active_repair_order_context={"order_id": int(result["id"])},
    )
    await state.set_state(ShopState.waiting_for_repair_context_comment)
    applied_count = len(result.get("applied") or {})
    conflict_count = len(result.get("conflicts") or {})
    lines = [f"✅ Данные со шильдика записаны в ремонт #{result['id']}."]
    if applied_count:
        lines.append(f"Заполнено полей: {applied_count}.")
    if conflict_count:
        lines.append(f"Конфликты оставил без перезаписи: {conflict_count}.")
    lines.append("")
    lines.append("Выберите частый диагноз кнопкой ниже или пришлите свободный комментарий текстом.")
    lines.append(
        "Например: «КЗ компрессора», «обрыв обмотки», «компрессор хрустит и выбивает автомат» "
        "или «после пайки вскрываются новые свищи теплообменника»."
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=_repair_context_keyboard())
    await callback.answer()


@router.callback_query(F.data == "repair_nameplate_cancel")
async def cancel_repair_nameplate(callback: CallbackQuery, state: FSMContext):
    await state.update_data(pending_repair_nameplate=None, pending_requisites_file=None)
    await state.set_state(None)
    await callback.message.edit_text("Ок, шильдик оставил без обработки.")
    await callback.answer()


@router.callback_query(F.data == "warranty_nameplate_start")
async def choose_warranty_nameplate_unit(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return
    if not str(pending.get("mime_type") or "").startswith("image/"):
        await callback.answer("Шильдик для гарантии распознаем только по фото.", show_alert=True)
        return

    await callback.message.edit_text(
        "Что фотографируем для гарантийного талона?",
        reply_markup=_warranty_unit_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("warranty_nameplate_unit_"))
async def choose_order_for_warranty_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    unit_type = str(callback.data or "").removeprefix("warranty_nameplate_unit_")
    if unit_type not in WARRANTY_UNIT_TYPES:
        await callback.answer("Не понял тип блока", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return

    await state.update_data(pending_warranty_nameplate={"unit_type": unit_type})
    response = await get_bot_api_gateway().list_warranty_nameplate_orders(
        telegram_id=callback.from_user.id,
        limit=5,
    )
    result = response.model_dump(mode="json")

    orders = result.get("items") or []
    if orders:
        await callback.message.edit_text(
            _format_warranty_nameplate_order_choices(orders, scope=str(result.get("scope") or ""), unit_type=unit_type),
            reply_markup=_warranty_nameplate_order_keyboard(orders),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ShopState.waiting_for_warranty_nameplate_order_id)
        unit_label = WARRANTY_UNIT_LABELS.get(unit_type, "блок")
        await callback.message.edit_text(
            f"Подходящих заказов в монтаже не нашел. Введите номер/id заказа для {unit_label} сообщением."
        )
    await callback.answer()


@router.callback_query(F.data == "warranty_nameplate_manual")
async def enter_order_id_for_warranty_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    draft = data.get("pending_warranty_nameplate") or {}
    if not isinstance(draft, dict) or draft.get("unit_type") not in WARRANTY_UNIT_TYPES:
        await callback.answer("Тип блока не выбран. Отправьте фото еще раз.", show_alert=True)
        return

    await state.set_state(ShopState.waiting_for_warranty_nameplate_order_id)
    await callback.message.edit_text("Введите номер/id заказа в монтаже сообщением.")
    await callback.answer()


async def _run_warranty_nameplate_recognition_for_order(
    progress_message: types.Message,
    *,
    order_id: int,
    telegram_user_id: int | None,
    can_attach_any: bool,
    state: FSMContext,
):
    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    draft = data.get("pending_warranty_nameplate") or {}
    unit_type = draft.get("unit_type") if isinstance(draft, dict) else None
    if unit_type not in WARRANTY_UNIT_TYPES:
        await progress_message.edit_text("Тип блока не выбран. Отправьте фото еще раз.")
        return
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await progress_message.edit_text("Фото не найдено. Отправьте его еще раз.")
        return

    try:
        content = await _download_telegram_file(
            str(pending.get("file_id")),
            expected_size=_normalize_file_size(pending.get("file_size")),
        )
        response = await get_bot_api_gateway().recognize_warranty_nameplate(
            telegram_id=int(telegram_user_id or 0),
            order_id=order_id,
            unit_type=str(unit_type),
            content=content,
            filename=str(pending.get("filename") or "telegram-warranty-nameplate.jpg"),
            mime_type=str(pending.get("mime_type") or "image/jpeg"),
        )
        recognized = response.model_dump(mode="json")
        merge_preview = recognized.get("merge_preview") or {}
    except BotApiNotFoundError:
        await progress_message.edit_text(
            "Этот заказ не найден среди монтажей или не назначен вам."
        )
        return
    except Exception as exc:
        await progress_message.edit_text(f"❌ Не удалось распознать шильдик для гарантии: {escape(str(exc))}")
        return

    draft = {
        "order_id": order_id,
        "unit_type": unit_type,
        "file": pending,
        "raw_text": recognized.get("raw_text") or "",
        "extracted": recognized.get("extracted") or {},
        "validation_flags": recognized.get("validation_flags") or {},
        "merge_preview": merge_preview or {"component": {"applied": {}, "conflicts": {}, "skipped": {}}},
    }
    await state.update_data(pending_warranty_nameplate=draft)
    await state.set_state(None)
    await progress_message.edit_text(
        _warranty_nameplate_preview_text(draft),
        reply_markup=_warranty_nameplate_preview_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("warranty_nameplate_order_"))
async def recognize_warranty_nameplate_for_chosen_order(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    order_id = _parse_order_id((callback.data or "").rsplit("_", 1)[-1])
    if not order_id:
        await callback.answer("Не понял номер заказа", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("Распознаю шильдик для гарантии…")
    await _run_warranty_nameplate_recognition_for_order(
        callback.message,
        order_id=order_id,
        telegram_user_id=callback.from_user.id,
        can_attach_any=context.is_manager,
        state=state,
    )


@router.message(ShopState.waiting_for_warranty_nameplate_order_id)
async def recognize_warranty_nameplate_for_typed_order(message: types.Message, state: FSMContext):
    context = await _get_bot_access_context(message.from_user.id if message.from_user else None)
    if not context.is_staff:
        await state.clear()
        return

    order_id = _parse_order_id(message.text)
    if not order_id:
        await message.answer("Введите номер заказа числом, например: 123")
        return

    progress = await message.answer("Распознаю шильдик для гарантии…")
    await _run_warranty_nameplate_recognition_for_order(
        progress,
        order_id=order_id,
        telegram_user_id=message.from_user.id if message.from_user else None,
        can_attach_any=context.is_manager,
        state=state,
    )


@router.callback_query(F.data == "warranty_nameplate_confirm")
async def confirm_warranty_nameplate(callback: CallbackQuery, state: FSMContext):
    context = await _get_bot_access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    draft = data.get("pending_warranty_nameplate") or {}
    if not isinstance(draft, dict) or not draft.get("order_id"):
        await callback.answer("Черновик не найден. Отправьте фото еще раз.", show_alert=True)
        return
    pending_file = draft.get("file") if isinstance(draft.get("file"), dict) else {}
    if not pending_file or not pending_file.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return

    try:
        file_content = await _download_telegram_file(
            str(pending_file.get("file_id")),
            expected_size=_normalize_file_size(pending_file.get("file_size")),
        )
        response = await get_bot_api_gateway().apply_warranty_nameplate(
                telegram_id=callback.from_user.id,
                order_id=int(draft["order_id"]),
                unit_type=str(draft.get("unit_type") or ""),
                content=file_content,
                extracted=draft.get("extracted") or {},
                raw_text=str(draft.get("raw_text") or ""),
                validation_flags=draft.get("validation_flags") or {},
                file_id=str(pending_file.get("file_id")),
                filename=str(pending_file.get("filename") or "telegram-warranty-nameplate.jpg"),
                mime_type=str(pending_file.get("mime_type") or "image/jpeg"),
                telegram_chat_id=pending_file.get("telegram_chat_id"),
                telegram_message_id=pending_file.get("telegram_message_id"),
            )
        result = response.result
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if not result:
        await callback.answer("Заказ не найден или недоступен.", show_alert=True)
        return

    await state.update_data(pending_warranty_nameplate=None, pending_requisites_file=None)
    await state.set_state(None)
    component_changes = len((result.get("component") or {}).get("applied") or {})
    equipment_changes = len((result.get("equipment") or {}).get("applied") or {})
    unit_label = WARRANTY_UNIT_LABELS.get(str(result.get("unit_type")), "блок")
    await callback.message.edit_text(
        f"✅ Шильдик для гарантии записан в заказ #{result['id']}.\n"
        f"Блок: {unit_label}.\n"
        f"Оборудование #{result['equipment_id']}, компонент #{result['component_id']}.\n"
        f"Заполнено полей: {component_changes + equipment_changes}."
    )
    await callback.answer()


@router.callback_query(F.data == "warranty_nameplate_cancel")
async def cancel_warranty_nameplate(callback: CallbackQuery, state: FSMContext):
    await state.update_data(pending_warranty_nameplate=None, pending_requisites_file=None)
    await state.set_state(None)
    await callback.message.edit_text("Ок, гарантийный шильдик оставил без обработки.")
    await callback.answer()
