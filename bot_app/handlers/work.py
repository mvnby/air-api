from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from html import escape
import os

from ..access_runtime import get_bot_access_context
from ..api_gateway import BotApiAuthorizationError, BotApiConflictError, BotApiError
from ..api_runtime import get_bot_api_gateway
from ..keyboards import (
    get_staff_main_menu,
    quick_order_confirm_keyboard,
    quick_order_scenario_keyboard,
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
    draft_session = await get_bot_api_gateway().start_quick_order_draft(
        telegram_id=message.from_user.id, text=""
    )
    await state.update_data(
        quick_order_draft_id=draft_session.draft_id,
        quick_order_version=draft_session.version,
    )
    await state.set_state(ShopState.editing_quick_order)
    await message.answer(
        "Выберите сценарий или пришлите текст заявки.\n"
        "Например: ООО Пример, обслуживание трёх кассетников, объект: Витебск, Московский 10.",
        reply_markup=quick_order_scenario_keyboard(
            draft_session.draft_id, draft_session.version, draft_session.scenarios
        ),
    )


async def _send_quick_order_preview(message: types.Message, draft_session) -> None:
    draft = quick_order_to_dict(draft_session.draft)
    keyboard = quick_order_confirm_keyboard(draft_session.draft_id, draft_session.version)
    chat_id = message.chat.id if message.chat else 0
    delivered = await BotTelegramService.send_rich_message(
        chat_id,
        format_quick_order_preview_rich_html(draft),
        reply_markup=keyboard,
    )
    if not delivered:
        await message.answer(
            format_quick_order_preview(draft), parse_mode="HTML", reply_markup=keyboard
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
    draft_session = await get_bot_api_gateway().start_quick_order_draft(
        telegram_id=message.from_user.id, text=text
    )
    await state.update_data(
        quick_order_draft_id=draft_session.draft_id,
        quick_order_version=draft_session.version,
    )
    await state.set_state(ShopState.editing_quick_order)
    await _send_quick_order_preview(message, draft_session)


@router.message(ShopState.editing_quick_order)
async def quick_order_edit_message(message: types.Message, state: FSMContext):
    context = await _require_staff(message)
    if not context or not context.is_manager:
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пришлите текст правки.")
        return
    data = await state.get_data()
    draft_id = data.get("quick_order_draft_id")
    version = data.get("quick_order_version")
    if not draft_id or not version:
        await message.answer("Черновик не найден. Начните новый быстрый заказ.")
        return
    field = data.get("quick_order_edit_field")
    if field == "customer_search":
        candidates = await get_bot_api_gateway().search_quick_order_customers(
            telegram_id=message.from_user.id, query=text
        )
        if not candidates.items:
            await message.answer("Совпадений нет. Уточните УНП, телефон или имя клиента.")
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{item.name[:35]} · {item.inn or item.phone or item.id}",
                callback_data=f"qo_customer:{draft_id}:{version}:{item.id}",
            )] for item in candidates.items
        ])
        await message.answer("Выберите точную карточку клиента:", reply_markup=keyboard)
        return
    changes = {field: text} if field in {"address", "name", "contact_name", "equipment_summary"} else None
    if changes and text.casefold() in {"убери", "удали", "неизвестно", "позже"}:
        changes[field] = None
    try:
        draft_session = await get_bot_api_gateway().patch_quick_order_draft(
            telegram_id=message.from_user.id, draft_id=draft_id,
            expected_version=int(version), text=None if changes else text, changes=changes,
        )
    except BotApiConflictError:
        current = await get_bot_api_gateway().get_quick_order_draft(
            telegram_id=message.from_user.id, draft_id=draft_id
        )
        await state.update_data(quick_order_version=current.version, quick_order_edit_field=None)
        await message.answer("Черновик уже изменился. Вот актуальная карточка; пришлите правку ещё раз.")
        await _send_quick_order_preview(message, current)
        return
    await state.update_data(quick_order_version=draft_session.version, quick_order_edit_field=None)
    await _send_quick_order_preview(message, draft_session)


@router.callback_query(F.data.startswith("qo_"))
async def quick_order_action(callback: CallbackQuery, state: FSMContext):
    context = await _access_context(callback.from_user.id)
    if not context.is_staff or not context.is_manager:
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Устаревшая кнопка", show_alert=True)
        return
    action, draft_id, raw_version = parts[:3]
    data = await state.get_data()
    if data.get("quick_order_draft_id") != draft_id:
        await callback.answer("Этот черновик уже закрыт", show_alert=True)
        return
    try:
        version = int(raw_version)
    except ValueError:
        await callback.answer("Устаревшая кнопка", show_alert=True)
        return
    if version != data.get("quick_order_version"):
        await callback.answer("Карточка обновилась. Используйте последние кнопки", show_alert=True)
        return
    gateway = get_bot_api_gateway()
    if action == "qo_scenarios":
        current = await gateway.get_quick_order_draft(
            telegram_id=callback.from_user.id, draft_id=draft_id
        )
        await callback.message.answer(
            "Выберите сценарий заказа:",
            reply_markup=quick_order_scenario_keyboard(draft_id, version, current.scenarios),
        )
        await callback.answer()
        return
    if action == "qo_select" and len(parts) == 4:
        code = parts[3]
        current = await gateway.get_quick_order_draft(
            telegram_id=callback.from_user.id, draft_id=draft_id
        )
        option = next((item for item in current.scenarios if (item.service_type or "works") == code), None)
        changes = {"workflow_type": option.workflow_type, "service_type": option.service_type} if option else None
        if changes is None:
            await callback.answer("Неизвестный сценарий", show_alert=True)
            return
        try:
            current = await gateway.patch_quick_order_draft(
                telegram_id=callback.from_user.id, draft_id=draft_id,
                expected_version=version, changes=changes,
            )
        except BotApiConflictError:
            await callback.answer("Карточка обновилась. Используйте последние кнопки", show_alert=True)
            return
        await state.update_data(quick_order_version=current.version)
        await _send_quick_order_preview(callback.message, current)
        await callback.answer()
        return
    if action == "qo_customer" and len(parts) == 4:
        try:
            customer_id = int(parts[3])
        except ValueError:
            await callback.answer("Клиент не найден", show_alert=True)
            return
        try:
            current = await gateway.patch_quick_order_draft(
                telegram_id=callback.from_user.id, draft_id=draft_id,
                expected_version=version, changes={"customer_id": customer_id},
            )
        except BotApiConflictError:
            await callback.answer("Карточка обновилась. Используйте последние кнопки", show_alert=True)
            return
        await state.update_data(quick_order_version=current.version, quick_order_edit_field=None)
        await _send_quick_order_preview(callback.message, current)
        await callback.answer()
        return
    if action in {"qo_edit", "qo_address", "qo_date", "qo_client", "qo_other"}:
        field = "address" if action == "qo_address" else "customer_search" if action == "qo_client" else None
        await state.update_data(quick_order_edit_field=field)
        prompt = {
            "qo_address": "Пришлите адрес объекта или «убери».",
            "qo_date": "Пришлите пожелание по дате или «дату убери».",
            "qo_client": "Пришлите УНП, телефон или имя для поиска клиента.",
            "qo_other": "Пришлите дополнительные сведения.",
        }.get(action, "Пришлите короткую правку, например «Не обслуживание, а ремонт».")
        await callback.message.answer(prompt)
        await callback.answer()
        return
    if action == "qo_cancel":
        try:
            await gateway.cancel_quick_order_draft(
                telegram_id=callback.from_user.id, draft_id=draft_id, expected_version=version
            )
        except BotApiConflictError:
            await callback.answer("Карточка обновилась. Используйте последние кнопки", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text("Быстрый заказ отменён.")
        await _answer_with_staff_menu(callback.message, context)
        await callback.answer()
        return
    if action == "qo_create":
        if data.get("quick_order_creating"):
            await callback.answer("Заказ уже создаётся")
            return
        await state.update_data(quick_order_creating=True)
        try:
            current = await gateway.get_quick_order_draft(
                telegram_id=callback.from_user.id, draft_id=draft_id
            )
            result = await gateway.create_quick_order_from_draft(
                telegram_id=callback.from_user.id, draft_id=draft_id,
                expected_version=version,
            )
        except BotApiError:
            await state.update_data(quick_order_creating=False)
            raise
        await state.clear()
        created_label = "создан" if result.created else "уже был создан"
        base_url = (os.getenv("MANAGER_BASE_URL") or os.getenv("PUBLIC_SITE_URL") or "https://mvn.by").rstrip("/")
        if base_url.endswith("/manager"):
            base_url = base_url[:-len("/manager")]
        order_url = f"{base_url}/manager/orders/kanban?orderId={result.order_id}"
        await callback.message.edit_text(
            f"✅ Заказ #{result.order_id} {created_label}. Сценарий: {escape(current.draft.service_label)}.\n"
            f'<a href="{escape(order_url)}">Открыть карточку</a>',
            parse_mode="HTML", disable_web_page_preview=True,
        )
        await _answer_with_staff_menu(callback.message, context)
        await callback.answer()
        return
    await callback.answer("Устаревшая кнопка", show_alert=True)


@router.callback_query(F.data.in_({"quick_order_create", "quick_order_retry", "quick_order_cancel"}))
async def quick_order_legacy_callback(callback: CallbackQuery):
    await callback.answer("Эта карточка устарела. Начните новый быстрый заказ.", show_alert=True)


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
