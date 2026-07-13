from html import escape

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from core.database import async_session_maker
from services.bot_access_service import BotAccessService
from services.bot_defect_act_service import BotDefectActService

from ..states import ShopState

router = Router()

REPAIR_PRESET_FAULT_TYPES = {
    "repair_preset_compressor_short": "compressor_short_circuit",
    "repair_preset_compressor_open": "compressor_winding_open",
    "repair_preset_compressor_mechanical": "compressor_mechanical_failure",
    "repair_preset_heat_exchanger_multiple": "heat_exchanger_multiple_leaks",
}


async def _access_context(user_id: int | None):
    async with async_session_maker() as session:
        return await BotAccessService.get_context(session, user_id)


def _parse_order_id(value: object) -> int | None:
    text = str(value or "").strip().lstrip("#").strip()
    if not text.isdigit():
        return None
    order_id = int(text)
    return order_id if order_id > 0 else None


def repair_context_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="КЗ компрессора", callback_data="repair_preset_compressor_short")],
            [InlineKeyboardButton(text="Обрыв обмотки", callback_data="repair_preset_compressor_open")],
            [InlineKeyboardButton(text="Механика компрессора", callback_data="repair_preset_compressor_mechanical")],
            [
                InlineKeyboardButton(
                    text="Множественные утечки",
                    callback_data="repair_preset_heat_exchanger_multiple",
                )
            ],
            [InlineKeyboardButton(text="Завершить заметки", callback_data="repair_context_finish")],
        ]
    )


def repair_comment_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Записать и продолжить", callback_data="repair_comment_confirm")],
            [InlineKeyboardButton(text="Не записывать", callback_data="repair_comment_cancel")],
            [InlineKeyboardButton(text="Завершить заметки", callback_data="repair_context_finish")],
        ]
    )


def repair_comment_preview_text(data: dict[str, object]) -> str:
    repair_meta = data.get("repair_meta") if isinstance(data.get("repair_meta"), dict) else {}
    merge_preview = data.get("merge_preview") if isinstance(data.get("merge_preview"), dict) else {}
    changes = merge_preview.get("changes") if isinstance(merge_preview.get("changes"), dict) else {}

    lines = ["<b>Проверьте дефектный акт перед записью:</b>"]
    preview_fields = (
        ("likely_diagnosis", "Диагноз"),
        ("inspection_work_done", "Проведено"),
        ("diagnostic_result", "Выявлено"),
        ("technical_conclusion", "Заключение"),
    )
    preview_values = 0
    for field, label in preview_fields:
        value = repair_meta.get(field)
        if value:
            lines.append(f"<b>{label}:</b> {escape(str(value))}")
            preview_values += 1

    preview_field_names = {field for field, _label in preview_fields}
    replacement_count = sum(
        1
        for field, values in changes.items()
        if field in preview_field_names
        and isinstance(values, dict)
        and values.get("existing") not in (None, "")
    )
    if replacement_count:
        lines.extend(["", f"Ранее заполненные данные будут обновлены: {replacement_count}."])
    if not preview_values:
        lines.extend(["", "Основные строки не заполнены. Лучше отправить комментарий подробнее."])
    return "\n".join(lines)


@router.callback_query(F.data.startswith("repair_preset_"))
async def prepare_repair_diagnostic_preset(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    fault_type = REPAIR_PRESET_FAULT_TYPES.get(str(callback.data or ""))
    if not fault_type:
        await callback.answer("Неизвестный вариант диагностики.", show_alert=True)
        return

    data = await state.get_data()
    active_context = data.get("active_repair_order_context") or {}
    order_id = _parse_order_id(active_context.get("order_id") if isinstance(active_context, dict) else None)
    if not order_id:
        await state.update_data(pending_repair_comment=None)
        await state.set_state(None)
        await callback.answer("Контекст ремонтного заказа потерян. Выберите заказ заново.", show_alert=True)
        return

    try:
        async with async_session_maker() as session:
            draft = await BotDefectActService.build_diagnostic_preset_draft(
                session,
                order_id=order_id,
                fault_type=fault_type,
            )
    except Exception as exc:
        await callback.answer(f"Не удалось подготовить дефектный акт: {exc}", show_alert=True)
        return

    if not isinstance(draft, dict):
        await callback.answer("Ремонтный заказ не найден. Выберите заказ заново.", show_alert=True)
        return

    await state.update_data(pending_repair_comment=draft)
    await state.set_state(ShopState.waiting_for_repair_context_comment)
    await callback.message.edit_text(
        repair_comment_preview_text(draft),
        reply_markup=repair_comment_preview_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ShopState.waiting_for_repair_context_comment)
async def handle_repair_context_comment(message: types.Message, state: FSMContext):
    context = await _access_context(message.from_user.id if message.from_user else None)
    if not context.is_staff:
        await state.clear()
        return

    text = str(message.text or "").strip()
    if not text:
        await message.answer("Пришлите диагностический комментарий текстом.")
        return
    if text.casefold() in {"стоп", "завершить", "готово", "отмена"}:
        await state.update_data(active_repair_order_context=None, pending_repair_comment=None)
        await state.set_state(None)
        await message.answer("Ок, вышел из режима заметок по ремонту.")
        return

    data = await state.get_data()
    active_context = data.get("active_repair_order_context") or {}
    order_id = _parse_order_id(active_context.get("order_id") if isinstance(active_context, dict) else None)
    if not order_id:
        await state.set_state(None)
        await message.answer("Контекст ремонтного заказа потерян. Отправьте шильдик или выберите заказ заново.")
        return

    progress = await message.answer("Готовлю краткий дефектный акт из комментария…")
    try:
        async with async_session_maker() as session:
            draft = await BotDefectActService.build_diagnostic_comment_draft(
                session,
                order_id=order_id,
                comment=text,
            )
    except Exception as exc:
        await progress.edit_text(f"❌ Не удалось обработать комментарий: {escape(str(exc))}")
        return

    if not draft:
        await progress.edit_text("Ремонтный заказ не найден. Выйдите из режима и выберите заказ заново.")
        return

    draft["telegram_message_id"] = message.message_id
    draft["telegram_chat_id"] = message.chat.id if message.chat else None
    await state.update_data(pending_repair_comment=draft)
    await progress.edit_text(
        repair_comment_preview_text(draft),
        reply_markup=repair_comment_preview_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "repair_comment_confirm")
async def confirm_repair_context_comment(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    if not context.is_staff:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    active_context = data.get("active_repair_order_context") or {}
    order_id = _parse_order_id(active_context.get("order_id") if isinstance(active_context, dict) else None)
    draft = data.get("pending_repair_comment") or {}
    if not order_id or not isinstance(draft, dict):
        await callback.answer("Черновик комментария не найден.", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await BotDefectActService.apply_diagnostic_comment(
            session,
            order_id,
            repair_meta_draft=draft.get("repair_meta") or {},
            raw_comment=str(draft.get("comment") or ""),
            telegram_user_id=callback.from_user.id,
            telegram_chat_id=draft.get("telegram_chat_id"),
            telegram_message_id=draft.get("telegram_message_id"),
            can_attach_any=context.is_manager,
        )

    if not result:
        await callback.answer("Заказ не найден или недоступен.", show_alert=True)
        return

    await state.update_data(pending_repair_comment=None)
    await state.set_state(ShopState.waiting_for_repair_context_comment)
    changed_count = len(result.get("changes") or {})
    await callback.message.edit_text(
        f"✅ Комментарий записан в ремонт #{result['id']}.\n"
        f"Обновлено полей: {changed_count}.\n\n"
        "Можно отправить следующий диагностический комментарий.",
        reply_markup=repair_context_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "repair_comment_cancel")
async def cancel_repair_context_comment(callback: CallbackQuery, state: FSMContext):
    await state.update_data(pending_repair_comment=None)
    await state.set_state(ShopState.waiting_for_repair_context_comment)
    await callback.message.edit_text(
        "Ок, комментарий не записал. Можно отправить следующий диагностический комментарий.",
        reply_markup=repair_context_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "repair_context_finish")
async def finish_repair_context(callback: CallbackQuery, state: FSMContext):
    await state.update_data(active_repair_order_context=None, pending_repair_comment=None)
    await state.set_state(None)
    await callback.message.edit_text("Ок, вышел из режима заметок по ремонту.")
    await callback.answer()
