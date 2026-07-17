from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ReplyKeyboardRemove

from ..access_runtime import get_bot_access_context
from ..api_gateway import BotApiAuthorizationError, BotApiConflictError, BotApiError
from ..api_runtime import get_bot_api_gateway
from ..keyboards import (
    get_staff_main_menu,
    quick_order_confirm_keyboard,
    selection_result_keyboard,
    task_actions_keyboard,
)
from ..quick_order_presenter import (
    format_quick_order_preview,
    format_quick_order_preview_rich_html,
    quick_order_to_dict,
)
from ..selection_presenter import format_client_selection, format_selection, format_selection_rich_html
from ..states import ShopState
from ..task_presenter import build_stage_report, format_tasks, format_tasks_rich_html, task_to_dict
from ..telegram_service import BotTelegramService

router = Router()


async def _access_context(user_id: int | None):
    return await get_bot_access_context(user_id)


async def _require_staff(message: types.Message):
    context = await _access_context(message.from_user.id if message.from_user else None)
    if not context.is_staff:
        await message.answer("Этот бот теперь только для сотрудников MVN.")
        return None
    return context


async def _answer_with_staff_menu(message: types.Message, context, text: str = "Можно продолжить работу из меню.") -> None:
    if context and context.is_staff:
        await message.answer(text, reply_markup=get_staff_main_menu(context))


@router.message(F.text == "⚡ Быстрый заказ")
@router.message(Command("quick_order"))
async def quick_order_start(message: types.Message, state: FSMContext):
    context = await _require_staff(message)
    if not context:
        return
    if not context.is_manager:
        await message.answer("Быстрый заказ доступен менеджерам и администраторам.")
        return
    await state.set_state(ShopState.waiting_for_quick_order)
    await message.answer(
        "Пришлите текст звонка одним сообщением.\n"
        "Например: ТО, Иван, +375 29 123-45-67, Победы 15, завтра 14:00",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ShopState.waiting_for_quick_order)
async def quick_order_parse(message: types.Message, state: FSMContext):
    context = await _require_staff(message)
    if not context or not context.is_manager:
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст заявки.")
        return
    response = await get_bot_api_gateway().parse_quick_order(
        telegram_id=message.from_user.id if message.from_user else 0,
        text=text,
    )
    draft = quick_order_to_dict(response.draft)
    chat_id = message.chat.id if message.chat else 0
    await state.update_data(
        quick_order_draft=draft,
        quick_order_idempotency_key=f"telegram:{chat_id}:{message.message_id}",
    )
    keyboard = quick_order_confirm_keyboard()
    fallback_text = format_quick_order_preview(draft)
    delivered = await BotTelegramService.send_rich_message(
        message.chat.id,
        format_quick_order_preview_rich_html(draft),
        reply_markup=keyboard,
    )
    if not delivered:
        await message.answer(fallback_text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "quick_order_create")
async def quick_order_create(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    if not context.is_staff or not context.is_manager:
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    data = await state.get_data()
    if data.get("quick_order_creating"):
        await callback.answer("Заказ уже создается", show_alert=False)
        return
    draft = data.get("quick_order_draft")
    idempotency_key = str(data.get("quick_order_idempotency_key") or "").strip()
    if not isinstance(draft, dict) or not idempotency_key:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    await state.update_data(quick_order_creating=True)
    try:
        result = await get_bot_api_gateway().create_quick_order(
            telegram_id=callback.from_user.id,
            idempotency_key=idempotency_key,
            draft=draft,
        )
    except BotApiError:
        await state.update_data(quick_order_creating=False)
        raise
    except ValueError as exc:
        await state.update_data(quick_order_creating=False)
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    created_label = "создан" if result.created else "уже был создан"
    await callback.message.edit_text(
        f"✅ Заказ #{result.order_id} {created_label}.\n"
        "Он уже доступен в менеджере и календаре, если дата была указана."
    )
    await _answer_with_staff_menu(callback.message, context)
    await callback.answer()


@router.callback_query(F.data == "quick_order_retry")
async def quick_order_retry(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ShopState.waiting_for_quick_order)
    await callback.message.answer("Пришлите исправленный текст заявки одним сообщением.")
    await callback.answer()


@router.callback_query(F.data == "quick_order_cancel")
async def quick_order_cancel(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("Быстрый заказ отменен.")
    await _answer_with_staff_menu(callback.message, context)
    await callback.answer()


@router.message(F.text == "🎯 Подбор")
@router.message(Command("selection"))
async def selection_start(message: types.Message, state: FSMContext):
    context = await _require_staff(message)
    if not context:
        return
    if not context.is_manager:
        await message.answer("Подбор для клиента доступен менеджерам и администраторам.")
        return
    await state.set_state(ShopState.waiting_for_selection)
    await message.answer(
        "Напишите запрос: например, 7х2, 7, 12 или 9 инвертора. "
        "Можно добавить: бюджетнее, премиум, ON-OFF, серверная.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ShopState.waiting_for_selection)
async def selection_process(message: types.Message, state: FSMContext):
    context = await _require_staff(message)
    if not context or not context.is_manager:
        await state.clear()
        return
    query = (message.text or "").strip()
    response = await get_bot_api_gateway().build_product_selection(
        telegram_id=message.from_user.id,
        query=query,
    )
    selection = response.selection
    await state.update_data(selection_client_text=format_client_selection(selection))
    await state.set_state(None)
    keyboard = selection_result_keyboard() if selection.get("areas") else None
    fallback_text = format_selection(selection)
    await BotTelegramService.send_rich_message(
        message.chat.id,
        format_selection_rich_html(selection),
        fallback_text=fallback_text,
        reply_markup=keyboard,
    )
    await message.answer("Готово. Можно продолжить работу из меню.", reply_markup=get_staff_main_menu(context))


@router.callback_query(F.data == "selection_client_text")
async def selection_client_text(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    if not context.is_staff or not context.is_manager:
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    data = await state.get_data()
    text = str(data.get("selection_client_text") or "").strip()
    if not text:
        await callback.answer("Подбор не найден", show_alert=True)
        return
    await callback.message.answer(text)
    await callback.answer("Можно переслать клиенту")


@router.message(F.text == "📅 Календарь")
async def calendar_hint(message: types.Message):
    context = await _require_staff(message)
    if not context:
        return
    await message.answer(
        "Календарь ведем в Manager. Быстрые заказы с датой автоматически появляются там.",
        reply_markup=get_staff_main_menu(context),
    )


@router.message(F.text == "🧰 Мои задачи")
@router.message(Command("tasks"))
async def my_tasks(message: types.Message):
    context = await _require_staff(message)
    if not context:
        return
    user_id = message.from_user.id if message.from_user else 0
    response = await get_bot_api_gateway().list_my_tasks(telegram_id=user_id, limit=10)
    tasks = [task_to_dict(task) for task in response.items]
    keyboard = task_actions_keyboard(tasks)
    fallback_text = format_tasks(tasks)
    delivered = await BotTelegramService.send_rich_message(
        message.chat.id,
        format_tasks_rich_html(tasks),
        reply_markup=keyboard,
    )
    if not delivered:
        await message.answer(fallback_text, parse_mode="HTML", reply_markup=keyboard)
    await _answer_with_staff_menu(message, context)


@router.callback_query(F.data.startswith("task_accept_") | F.data.startswith("task_done_"))
async def update_task_status(callback: CallbackQuery):
    context = await _access_context(callback.from_user.id)
    data = callback.data or ""
    status = "in_progress" if data.startswith("task_accept_") else "completed"
    stage_id = int(data.rsplit("_", 1)[-1])
    try:
        await get_bot_api_gateway().update_task_status(
            telegram_id=callback.from_user.id,
            stage_id=stage_id,
            status=status,
        )
    except BotApiAuthorizationError:
        await callback.answer("Задача не найдена или нет доступа", show_alert=True)
        return
    except BotApiConflictError:
        await callback.answer("Задача уже завершена или отменена", show_alert=True)
        return
    await callback.answer("Готово")
    await callback.message.answer("Статус задачи обновлен.", reply_markup=get_staff_main_menu(context))


@router.callback_query(F.data.startswith("task_report_"))
async def task_report_start(callback: CallbackQuery, state: FSMContext):
    stage_id = int((callback.data or "").rsplit("_", 1)[-1])
    await state.update_data(task_report_stage_id=stage_id)
    await state.set_state(ShopState.waiting_for_task_report)
    await callback.message.answer("Пришлите комментарий/отчет по задаче: текст, фото или документ с подписью.")
    await callback.answer()


@router.message(ShopState.waiting_for_task_report)
async def task_report_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    stage_id = int(data.get("task_report_stage_id") or 0)
    photo_file_id = message.photo[-1].file_id if message.photo else None
    document = message.document
    report = build_stage_report(
        text=message.text,
        caption=message.caption,
        photo_file_id=photo_file_id,
        document_file_id=document.file_id if document else None,
        document_name=document.file_name if document else None,
    )
    if not stage_id or not report:
        await message.answer("Отчет пустой, попробуйте еще раз.")
        return
    try:
        await get_bot_api_gateway().save_task_report(
            telegram_id=message.from_user.id if message.from_user else 0,
            stage_id=stage_id,
            report=report,
        )
    except BotApiAuthorizationError:
        await state.clear()
        context = await _access_context(message.from_user.id if message.from_user else None)
        await message.answer(
            "Задача не найдена или нет доступа.",
            reply_markup=get_staff_main_menu(context) if context.is_staff else None,
        )
        return
    await state.clear()
    context = await _access_context(message.from_user.id if message.from_user else None)
    await message.answer(
        "Отчет сохранен.",
        reply_markup=get_staff_main_menu(context) if context.is_staff else None,
    )
