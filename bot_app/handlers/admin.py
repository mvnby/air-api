from io import BytesIO
from html import escape
import os
import re
import secrets

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from core.database import async_session_maker
from services.product_service import ProductService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.bot_warranty_nameplate_service import BotWarrantyNameplateService
from services.bot_task_service import BotTaskService
from ..access_runtime import get_bot_access_context
from .repair_context import repair_context_keyboard as _repair_context_keyboard
from ..config import bot
from ..states import ShopState

router = Router()


async def _is_admin_user(user_id: int | None) -> bool:
    context = await _get_bot_access_context(user_id)
    return context.is_staff and context.is_manager


async def _get_bot_access_context(user_id: int | None):
    return await get_bot_access_context(user_id)


async def _is_staff_user(user_id: int | None) -> bool:
    context = await _get_bot_access_context(user_id)
    return context.is_staff


def _manager_customer_url(customer_id: int) -> str:
    base_url = (
        os.getenv("MANAGER_BASE_URL")
        or os.getenv("PUBLIC_SITE_URL")
        or "https://mvn.by"
    ).rstrip("/")
    return f"{base_url}/manager/customers/profile?customerId={customer_id}"


def _preview_text(data: dict) -> str:
    extracted = data.get("extracted") or {}
    flags = data.get("validation_flags") or {}
    field_errors = flags.get("field_errors") or {}
    warnings = flags.get("warnings") or {}
    duplicate = data.get("duplicate_customer")

    lines = ["<b>Распознал реквизиты. Проверьте перед созданием клиента:</b>", ""]
    fields = [
        ("name", "Клиент", extracted.get("name")),
        ("inn", "УНП", extracted.get("inn")),
        ("legal_address", "Юр. адрес", extracted.get("legal_address")),
        ("bank_name", "Банк", extracted.get("bank_name")),
        ("bic", "БИК", extracted.get("bic")),
        ("iban", "IBAN", extracted.get("iban")),
        ("phone", "Телефон", extracted.get("phone") or extracted.get("phone_raw")),
        ("email", "Email", extracted.get("email")),
        ("signer_name", "Подписант", extracted.get("signer_name")),
        ("signer_position", "Должность", extracted.get("signer_position")),
        ("acting_basis", "Основание", extracted.get("acting_basis")),
    ]
    for field, label, value in fields:
        marker = " ⚠️" if field in field_errors else ""
        lines.append(f"<b>{escape(label)}:</b>{marker} {escape(str(value or '—'))}")

    extra = extracted.get("extra") or {}
    if extra.get("okpo"):
        lines.append(f"<b>ОКПО:</b> {escape(str(extra.get('okpo')))}")
    if extra.get("bank_address"):
        lines.append(f"<b>Адрес банка:</b> {escape(str(extra.get('bank_address')))}")

    if duplicate:
        lines.extend(["", f"⚠️ Клиент с таким УНП уже есть: <b>{escape(str(duplicate.get('name') or duplicate.get('id')))}</b>"])
    if field_errors:
        lines.extend(["", "<b>Ошибки:</b>"])
        lines.extend(f"• {escape(field)}: {escape(str(message))}" for field, message in field_errors.items())
    if warnings:
        lines.extend(["", "<b>Предупреждения:</b>"])
        lines.extend(f"• {escape(str(message))}" for message in warnings.values())
    return "\n".join(lines)


def _preview_keyboard(data: dict) -> InlineKeyboardMarkup:
    recognition_id = int(data["id"])
    buttons: list[list[InlineKeyboardButton]] = []
    duplicate = data.get("duplicate_customer")
    field_errors = ((data.get("validation_flags") or {}).get("field_errors") or {})
    if not field_errors:
        buttons.append([InlineKeyboardButton(text="Создать клиента", callback_data=f"ocr_create_{recognition_id}")])
        if duplicate:
            buttons.append([InlineKeyboardButton(text="Обновить существующего", callback_data=f"ocr_update_{recognition_id}")])
    buttons.append([InlineKeyboardButton(text="Отменить", callback_data=f"ocr_cancel_{recognition_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _looks_like_requisites_text(text: str | None) -> bool:
    normalized = str(text or "").strip()
    if len(normalized) < 40:
        return False
    lowered = normalized.casefold()
    markers = (
        "унп",
        "р/с",
        "расчетный счет",
        "расчётный счет",
        "iban",
        "bic",
        "банк",
        "банковские реквизиты",
        "юридический адрес",
        "почтовый адрес",
        "свидетельство",
    )
    marker_count = sum(1 for marker in markers if marker in lowered)
    has_unp = bool(re.search(r"\bунп\s*\d{9}\b", lowered))
    has_iban = bool(re.search(r"\bBY[0-9A-ZА-ЯЁ ]{20,40}\b", normalized, flags=re.IGNORECASE))
    has_bic = bool(re.search(r"\bBIC\s+[A-Z0-9]{8,11}\b", normalized, flags=re.IGNORECASE))
    return marker_count >= 2 or has_iban or (has_unp and marker_count >= 1) or (has_unp and has_bic)


def _requisites_file_intent_keyboard(
    *,
    can_extract_requisites: bool = True,
    can_repair_nameplate: bool = False,
    can_warranty_nameplate: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_extract_requisites:
        rows.append([InlineKeyboardButton(text="Извлечь реквизиты", callback_data="req_file_extract")])
    if can_repair_nameplate:
        rows.append([InlineKeyboardButton(text="Шильдик к ремонту", callback_data="repair_nameplate_start")])
    if can_warranty_nameplate:
        rows.append([InlineKeyboardButton(text="Шильдик для гарантии", callback_data="warranty_nameplate_start")])
    rows.append([InlineKeyboardButton(text="Прикрепить к заказу", callback_data="req_file_attach")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="req_file_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _order_attachment_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        if not order_id:
            continue
        title = " ".join(str(order.get("title") or order.get("customer_name") or "заказ").split())
        if len(title) > 36:
            title = f"{title[:33]}..."
        rows.append(
            [InlineKeyboardButton(text=f"#{order_id} - {title}", callback_data=f"req_file_attach_order_{order_id}")]
        )
    rows.append([InlineKeyboardButton(text="Ввести номер/id заказа", callback_data="req_file_attach_manual")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="req_file_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _repair_nameplate_order_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        if not order_id:
            continue
        title = " ".join(str(order.get("title") or order.get("customer_name") or "ремонт").split())
        if len(title) > 34:
            title = f"{title[:31]}..."
        rows.append(
            [InlineKeyboardButton(text=f"#{order_id} - {title}", callback_data=f"repair_nameplate_order_{order_id}")]
        )
    rows.append([InlineKeyboardButton(text="Ввести номер/id заказа", callback_data="repair_nameplate_manual")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="repair_nameplate_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _warranty_unit_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Внутренний блок", callback_data="warranty_nameplate_unit_indoor_unit")],
            [InlineKeyboardButton(text="Наружный блок", callback_data="warranty_nameplate_unit_outdoor_unit")],
            [InlineKeyboardButton(text="Отмена", callback_data="warranty_nameplate_cancel")],
        ]
    )


def _warranty_nameplate_order_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        if not order_id:
            continue
        title = " ".join(str(order.get("title") or order.get("customer_name") or "монтаж").split())
        if len(title) > 34:
            title = f"{title[:31]}..."
        rows.append(
            [InlineKeyboardButton(text=f"#{order_id} - {title}", callback_data=f"warranty_nameplate_order_{order_id}")]
        )
    rows.append([InlineKeyboardButton(text="Ввести номер/id заказа", callback_data="warranty_nameplate_manual")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="warranty_nameplate_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_order_attachment_choices(orders: list[dict]) -> str:
    if not orders:
        return "Быстрых вариантов не нашел. Введите номер/id заказа сообщением."

    lines = ["К какому заказу прикрепить файл?"]
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        customer = order.get("customer_name") or "клиент не указан"
        title = order.get("title") or "заказ"
        address = order.get("address") or "адрес не указан"
        lines.append(f"#{order_id}: {escape(str(title))}, {escape(str(customer))}, {escape(str(address))}")
    return "\n".join(lines)


def _format_repair_nameplate_order_choices(orders: list[dict]) -> str:
    if not orders:
        return "Быстрых активных ремонтных заказов не нашел. Введите номер/id заказа сообщением."

    lines = ["К какому ремонтному заказу добавить данные со шильдика?"]
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        customer = order.get("customer_name") or "клиент не указан"
        title = order.get("title") or "ремонт"
        address = order.get("address") or "адрес не указан"
        lines.append(f"#{order_id}: {escape(str(title))}, {escape(str(customer))}, {escape(str(address))}")
    return "\n".join(lines)


def _format_warranty_nameplate_order_choices(orders: list[dict], *, scope: str, unit_type: str) -> str:
    unit_label = BotWarrantyNameplateService.UNIT_LABELS.get(unit_type, "блок")
    if not orders:
        return f"Подходящих заказов в монтаже не нашел. Введите номер/id заказа для {escape(unit_label)} сообщением."

    heading = (
        f"К какому сегодняшнему монтажу привязать {unit_label}?"
        if scope == "today"
        else f"Сегодняшних монтажей не нашел. Выберите заказ в состоянии монтаж для {unit_label}:"
    )
    lines = [heading]
    for order in orders[:5]:
        order_id = int(order.get("id") or 0)
        customer = order.get("customer_name") or "клиент не указан"
        title = order.get("title") or "монтаж"
        address = order.get("address") or "адрес не указан"
        date = order.get("installation_date")
        date_text = date.strftime("%d.%m %H:%M") if hasattr(date, "strftime") else ""
        suffix = f", {escape(date_text)}" if date_text else ""
        lines.append(f"#{order_id}: {escape(str(title))}, {escape(str(customer))}, {escape(str(address))}{suffix}")
    return "\n".join(lines)


def _order_choices_from_tasks(tasks: list[dict]) -> list[dict]:
    choices: list[dict] = []
    seen: set[int] = set()
    for task in tasks:
        order_id = int(task.get("order_id") or task.get("id") or 0)
        if not order_id or order_id in seen:
            continue
        seen.add(order_id)
        choices.append(
            {
                "id": order_id,
                "title": task.get("title") or "заказ",
                "customer_name": task.get("customer_name"),
                "address": task.get("address"),
            }
        )
    return choices


def _parse_order_id(text: str | None) -> int | None:
    cleaned = str(text or "").strip().lstrip("#").strip()
    if not cleaned.isdigit():
        return None
    order_id = int(cleaned)
    return order_id if order_id > 0 else None


def _repair_nameplate_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Записать в ремонт", callback_data="repair_nameplate_confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="repair_nameplate_cancel")],
        ]
    )


def _warranty_nameplate_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Записать в гарантию", callback_data="warranty_nameplate_confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="warranty_nameplate_cancel")],
        ]
    )


def _serial_candidate_preview_lines(extracted: dict, validation_flags: dict) -> list[str]:
    candidates = validation_flags.get("serial_candidates")
    if not isinstance(candidates, list) or len(candidates) <= 1:
        return []
    selected = str(extracted.get("equipment_serial_number") or "")
    lines = ["", "<b>Возможные серийные номера:</b>"]
    for candidate in candidates[:5]:
        candidate_text = str(candidate)
        suffix = " (выбран)" if candidate_text == selected else ""
        lines.append(f"• {escape(candidate_text)}{escape(suffix)}")
    return lines


def _format_iso_date_ru(value: object) -> str:
    text = str(value or "")
    parts = text.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return text


def _serial_details_preview_lines(validation_flags: dict) -> list[str]:
    details = validation_flags.get("serial_details")
    if not isinstance(details, dict) or details.get("format") != "tcl_factory_20":
        return []
    lines = ["", "<b>Расшифровка серийника TCL:</b>"]
    production_date = details.get("production_date")
    if production_date:
        lines.append(f"• дата производства: {escape(_format_iso_date_ru(production_date))}")
    unit_type_label = details.get("unit_type_label")
    if unit_type_label:
        lines.append(f"• тип блока по коду: {escape(str(unit_type_label))}")
    batch_code = details.get("batch_code")
    if batch_code:
        lines.append(f"• партия: {escape(str(batch_code))}")
    product_serial_number = details.get("product_serial_number")
    if product_serial_number:
        lines.append(f"• порядковый номер: {escape(str(product_serial_number))}")
    return lines


def _repair_nameplate_preview_text(data: dict[str, object]) -> str:
    extracted = data.get("extracted") if isinstance(data.get("extracted"), dict) else {}
    validation_flags = data.get("validation_flags") if isinstance(data.get("validation_flags"), dict) else {}
    merge_preview = data.get("merge_preview") if isinstance(data.get("merge_preview"), dict) else {}
    applied = merge_preview.get("applied") if isinstance(merge_preview.get("applied"), dict) else {}
    conflicts = merge_preview.get("conflicts") if isinstance(merge_preview.get("conflicts"), dict) else {}
    skipped = merge_preview.get("skipped") if isinstance(merge_preview.get("skipped"), dict) else {}
    warnings = validation_flags.get("warnings") if isinstance(validation_flags.get("warnings"), dict) else {}

    lines = ["<b>Распознал шильдик. Проверьте перед записью:</b>", ""]
    for field in BotRepairNameplateService.REPAIR_FIELDS:
        label = BotRepairNameplateService.FIELD_LABELS.get(field, field)
        value = extracted.get(field)
        if value:
            lines.append(f"<b>{escape(label)}:</b> {escape(str(value))}")
    lines.extend(_serial_candidate_preview_lines(extracted, validation_flags))
    lines.extend(_serial_details_preview_lines(validation_flags))

    if applied:
        lines.extend(["", "<b>Будет записано:</b>"])
        lines.extend(
            f"• {escape(BotRepairNameplateService.FIELD_LABELS.get(field, field))}: {escape(str(value))}"
            for field, value in applied.items()
        )
    if skipped:
        lines.extend(["", "<b>Уже было заполнено таким же значением:</b>"])
        lines.extend(
            f"• {escape(BotRepairNameplateService.FIELD_LABELS.get(field, field))}: {escape(str(value))}"
            for field, value in skipped.items()
        )
    if conflicts:
        lines.extend(["", "<b>Конфликты, не перезапишу автоматически:</b>"])
        for field, values in conflicts.items():
            label = BotRepairNameplateService.FIELD_LABELS.get(field, field)
            existing = values.get("existing") if isinstance(values, dict) else ""
            candidate = values.get("candidate") if isinstance(values, dict) else ""
            lines.append(f"• {escape(label)}: сейчас {escape(str(existing))}, распознано {escape(str(candidate))}")
    if warnings:
        lines.extend(["", "<b>Предупреждения:</b>"])
        lines.extend(f"• {escape(str(message))}" for message in warnings.values())
    if not extracted:
        lines.append("Данных не нашел. Лучше отправить фото ближе и ровнее.")
    return "\n".join(lines)


def _warranty_nameplate_preview_text(data: dict[str, object]) -> str:
    extracted = data.get("extracted") if isinstance(data.get("extracted"), dict) else {}
    validation_flags = data.get("validation_flags") if isinstance(data.get("validation_flags"), dict) else {}
    merge_preview = data.get("merge_preview") if isinstance(data.get("merge_preview"), dict) else {}
    component = merge_preview.get("component") if isinstance(merge_preview.get("component"), dict) else {}
    equipment = merge_preview.get("equipment") if isinstance(merge_preview.get("equipment"), dict) else {}
    warnings = validation_flags.get("warnings") if isinstance(validation_flags.get("warnings"), dict) else {}
    unit_label = merge_preview.get("unit_label") or BotWarrantyNameplateService.UNIT_LABELS.get(str(data.get("unit_type")), "блок")

    lines = [f"<b>Распознал шильдик для гарантии: {escape(str(unit_label))}.</b>", ""]
    fields = {
        "brand": extracted.get("equipment_brand"),
        "model": extracted.get("equipment_model"),
        "serial": extracted.get("equipment_serial_number"),
        "refrigerant_type": extracted.get("refrigerant_type"),
    }
    for field, value in fields.items():
        if value:
            lines.append(f"<b>{escape(BotWarrantyNameplateService.FIELD_LABELS.get(field, field))}:</b> {escape(str(value))}")
    lines.extend(_serial_candidate_preview_lines(extracted, validation_flags))
    lines.extend(_serial_details_preview_lines(validation_flags))

    if merge_preview.get("will_create_equipment"):
        lines.extend(["", "Создам карточку оборудования из заказа, если ее еще нет."])
    if merge_preview.get("will_create_component"):
        lines.append("Создам компонент выбранного блока.")

    applied = component.get("applied") if isinstance(component.get("applied"), dict) else {}
    conflicts = component.get("conflicts") if isinstance(component.get("conflicts"), dict) else {}
    skipped = component.get("skipped") if isinstance(component.get("skipped"), dict) else {}
    equipment_applied = equipment.get("applied") if isinstance(equipment.get("applied"), dict) else {}
    if applied or equipment_applied:
        lines.extend(["", "<b>Будет записано:</b>"])
        for field, value in applied.items():
            lines.append(f"• {escape(BotWarrantyNameplateService.FIELD_LABELS.get(field, field))}: {escape(str(value))}")
        for field, value in equipment_applied.items():
            lines.append(f"• карточка: {escape(BotWarrantyNameplateService.FIELD_LABELS.get(field, field))}: {escape(str(value))}")
    if skipped:
        lines.extend(["", "<b>Уже заполнено таким же значением:</b>"])
        for field in skipped.keys():
            lines.append(f"• {escape(BotWarrantyNameplateService.FIELD_LABELS.get(field, field))}")
    if conflicts:
        lines.extend(["", "<b>Конфликты, не перезапишу автоматически:</b>"])
        for field, values in conflicts.items():
            existing = values.get("existing") if isinstance(values, dict) else ""
            candidate = values.get("candidate") if isinstance(values, dict) else ""
            lines.append(
                f"• {escape(BotWarrantyNameplateService.FIELD_LABELS.get(field, field))}: "
                f"сейчас {escape(str(existing))}, распознано {escape(str(candidate))}"
            )
    if warnings:
        lines.extend(["", "<b>Предупреждения:</b>"])
        lines.extend(f"• {escape(str(message))}" for message in warnings.values())
    return "\n".join(lines)


def _file_too_large_message(max_bytes: int = CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES) -> str:
    max_mb = max_bytes / (1024 * 1024)
    return f"Файл слишком большой. Максимум {max_mb:g} МБ."


def _normalize_file_size(value: object) -> int | None:
    try:
        size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


async def _download_telegram_file(file_id: str, *, expected_size: int | None = None) -> bytes:
    max_bytes = CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES
    if expected_size is not None and expected_size > max_bytes:
        raise ValueError(_file_too_large_message(max_bytes))

    telegram_file = await bot.get_file(file_id)
    actual_size = _normalize_file_size(getattr(telegram_file, "file_size", None))
    if expected_size is None and actual_size is None:
        raise ValueError("Telegram не вернул размер файла.")
    if actual_size is not None and actual_size > max_bytes:
        raise ValueError(_file_too_large_message(max_bytes))
    file_path = getattr(telegram_file, "file_path", None)
    if not file_path:
        raise ValueError("Telegram не вернул путь к файлу.")

    buffer = BytesIO()
    await bot.download_file(file_path, destination=buffer)
    content = buffer.getvalue()
    if len(content) > max_bytes:
        raise ValueError(_file_too_large_message(max_bytes))
    return content


async def _run_requisites_recognition(
    progress_message: types.Message,
    *,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
    telegram_user_id: int | None,
    telegram_chat_id: int | None,
    telegram_message_id: int | None,
):
    try:
        content = await _download_telegram_file(file_id, expected_size=_normalize_file_size(file_size))
        async with async_session_maker() as session:
            data = await CustomerRequisitesRecognitionService.recognize_bytes(
                session,
                content=content,
                filename=filename,
                mime_type=mime_type,
                source="telegram",
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
    except Exception as exc:
        await progress_message.edit_text(f"❌ Не удалось распознать реквизиты: {escape(str(exc))}")
        return

    await progress_message.edit_text(_preview_text(data), reply_markup=_preview_keyboard(data), parse_mode="HTML")


async def _run_requisites_text_recognition(
    progress_message: types.Message,
    *,
    text: str,
    telegram_user_id: int | None,
    telegram_chat_id: int | None,
    telegram_message_id: int | None,
):
    try:
        async with async_session_maker() as session:
            data = await CustomerRequisitesRecognitionService.recognize_text(
                session,
                text=text,
                source="telegram_text",
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
    except Exception as exc:
        await progress_message.edit_text(f"❌ Не удалось распознать реквизиты: {escape(str(exc))}")
        return

    await progress_message.edit_text(_preview_text(data), reply_markup=_preview_keyboard(data), parse_mode="HTML")


async def _handle_requisites_file(
    message: types.Message,
    *,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
):
    user_id = telegram_user_id if telegram_user_id is not None else (message.from_user.id if message.from_user else None)
    if not await _is_admin_user(user_id):
        await message.answer("Распознавание реквизитов доступно только администраторам.")
        return

    progress = await message.answer("Распознаю реквизиты…")
    await _run_requisites_recognition(
        progress,
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        file_size=file_size,
        telegram_user_id=user_id,
        telegram_chat_id=telegram_chat_id if telegram_chat_id is not None else (message.chat.id if message.chat else None),
        telegram_message_id=telegram_message_id if telegram_message_id is not None else message.message_id,
    )


async def _ask_requisites_file_action(
    message: types.Message,
    state: FSMContext,
    *,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
):
    user_id = message.from_user.id if message.from_user else None
    if not await _is_staff_user(user_id):
        await message.answer(
            "Файл получил, но действия с файлами доступны только сотрудникам."
        )
        return
    normalized_size = _normalize_file_size(file_size)
    if normalized_size is not None and normalized_size > CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES:
        await message.answer(_file_too_large_message())
        return
    can_extract_requisites = await _is_admin_user(user_id)

    await state.update_data(
        pending_requisites_file={
            "file_id": file_id,
            "filename": filename,
            "mime_type": mime_type,
            "file_size": normalized_size,
            "telegram_message_id": message.message_id,
            "telegram_chat_id": message.chat.id if message.chat else None,
        }
    )
    await message.answer(
        "Файл получил. Что сделать?",
        reply_markup=_requisites_file_intent_keyboard(
            can_extract_requisites=can_extract_requisites,
            can_repair_nameplate=str(mime_type or "").startswith("image/"),
            can_warranty_nameplate=str(mime_type or "").startswith("image/"),
        ),
    )


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

    async with async_session_maker() as session:
        if context.is_manager:
            orders = await BotOrderAttachmentService.list_recent_orders(session, limit=5)
        else:
            tasks = await BotTaskService.list_my_tasks(session, callback.from_user.id, limit=5)
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

    async with async_session_maker() as session:
        allowed = await BotOrderAttachmentService.can_attach_to_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
        if not allowed:
            return {"forbidden": True}
        try:
            content = await _download_telegram_file(
                str(pending.get("file_id")),
                expected_size=_normalize_file_size(pending.get("file_size")),
            )
        except Exception as exc:
            return {"error": str(exc)}
        return await BotOrderAttachmentService.attach_to_order(
            session,
            order_id,
            file_id=str(pending.get("file_id")),
            filename=str(pending.get("filename") or "telegram-file"),
            mime_type=str(pending.get("mime_type") or "application/octet-stream"),
            telegram_user_id=telegram_user_id,
            telegram_chat_id=pending.get("telegram_chat_id"),
            telegram_message_id=pending.get("telegram_message_id"),
            content=content,
        )


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

    async with async_session_maker() as session:
        orders = await BotRepairNameplateService.list_repair_orders(
            session,
            telegram_user_id=callback.from_user.id,
            can_attach_any=context.is_manager,
            limit=5,
        )

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

    async with async_session_maker() as session:
        allowed = await BotRepairNameplateService.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
    if not allowed:
        await progress_message.edit_text(
            "Этот заказ не найден среди активных ремонтных заказов или не назначен вам."
        )
        return

    try:
        content = await _download_telegram_file(
            str(pending.get("file_id")),
            expected_size=_normalize_file_size(pending.get("file_size")),
        )
        recognized = await BotRepairNameplateService.recognize_bytes(
            content=content,
            filename=str(pending.get("filename") or "telegram-nameplate.jpg"),
            mime_type=str(pending.get("mime_type") or "image/jpeg"),
        )
        async with async_session_maker() as session:
            merge_preview = await BotRepairNameplateService.build_merge_preview(
                session,
                order_id=order_id,
                extracted=recognized.get("extracted") or {},
            )
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
        async with async_session_maker() as session:
            result = await BotRepairNameplateService.apply_to_order(
                session,
                int(draft["order_id"]),
                extracted=draft.get("extracted") or {},
                raw_text=str(draft.get("raw_text") or ""),
                validation_flags=draft.get("validation_flags") or {},
                file_id=str(pending_file.get("file_id")),
                filename=str(pending_file.get("filename") or "telegram-nameplate.jpg"),
                mime_type=str(pending_file.get("mime_type") or "image/jpeg"),
                telegram_user_id=callback.from_user.id,
                telegram_chat_id=pending_file.get("telegram_chat_id"),
                telegram_message_id=pending_file.get("telegram_message_id"),
                can_attach_any=context.is_manager,
                file_content=file_content,
            )
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
    if unit_type not in BotWarrantyNameplateService.UNIT_TYPES:
        await callback.answer("Не понял тип блока", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_requisites_file") or {}
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await callback.answer("Фото не найдено. Отправьте его еще раз.", show_alert=True)
        return

    await state.update_data(pending_warranty_nameplate={"unit_type": unit_type})
    async with async_session_maker() as session:
        result = await BotWarrantyNameplateService.list_installation_orders(
            session,
            telegram_user_id=callback.from_user.id,
            can_attach_any=context.is_manager,
            limit=5,
        )

    orders = result.get("items") or []
    if orders:
        await callback.message.edit_text(
            _format_warranty_nameplate_order_choices(orders, scope=str(result.get("scope") or ""), unit_type=unit_type),
            reply_markup=_warranty_nameplate_order_keyboard(orders),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ShopState.waiting_for_warranty_nameplate_order_id)
        unit_label = BotWarrantyNameplateService.UNIT_LABELS.get(unit_type, "блок")
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
    if not isinstance(draft, dict) or draft.get("unit_type") not in BotWarrantyNameplateService.UNIT_TYPES:
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
    if unit_type not in BotWarrantyNameplateService.UNIT_TYPES:
        await progress_message.edit_text("Тип блока не выбран. Отправьте фото еще раз.")
        return
    if not isinstance(pending, dict) or not pending.get("file_id"):
        await progress_message.edit_text("Фото не найдено. Отправьте его еще раз.")
        return

    async with async_session_maker() as session:
        allowed = await BotWarrantyNameplateService.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
    if not allowed:
        await progress_message.edit_text(
            "Этот заказ не найден среди монтажей или не назначен вам."
        )
        return

    try:
        content = await _download_telegram_file(
            str(pending.get("file_id")),
            expected_size=_normalize_file_size(pending.get("file_size")),
        )
        recognized = await BotRepairNameplateService.recognize_bytes(
            content=content,
            filename=str(pending.get("filename") or "telegram-warranty-nameplate.jpg"),
            mime_type=str(pending.get("mime_type") or "image/jpeg"),
        )
        async with async_session_maker() as session:
            merge_preview = await BotWarrantyNameplateService.build_merge_preview(
                session,
                order_id=order_id,
                unit_type=str(unit_type),
                extracted=recognized.get("extracted") or {},
            )
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
        async with async_session_maker() as session:
            result = await BotWarrantyNameplateService.apply_to_order(
                session,
                int(draft["order_id"]),
                unit_type=str(draft.get("unit_type") or ""),
                extracted=draft.get("extracted") or {},
                raw_text=str(draft.get("raw_text") or ""),
                validation_flags=draft.get("validation_flags") or {},
                file_id=str(pending_file.get("file_id")),
                filename=str(pending_file.get("filename") or "telegram-warranty-nameplate.jpg"),
                mime_type=str(pending_file.get("mime_type") or "image/jpeg"),
                telegram_user_id=callback.from_user.id,
                telegram_chat_id=pending_file.get("telegram_chat_id"),
                telegram_message_id=pending_file.get("telegram_message_id"),
                can_attach_any=context.is_manager,
                file_content=file_content,
            )
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
    unit_label = BotWarrantyNameplateService.UNIT_LABELS.get(str(result.get("unit_type")), "блок")
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
        async with async_session_maker() as session:
            if action == "cancel":
                await CustomerRequisitesRecognitionService.cancel(session, recognition_id=recognition_id)
                await callback.message.edit_text("Распознавание отменено.")
                await callback.answer()
                return
            result = await CustomerRequisitesRecognitionService.confirm(
                session,
                recognition_id=recognition_id,
                action=action,
            )
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    customer = result["customer"]
    customer_id = int(customer["id"])
    await callback.message.edit_text(
        f"✅ Клиент {'создан' if action == 'create' else 'обновлен'}: "
        f"<a href=\"{escape(_manager_customer_url(customer_id))}\">{escape(str(customer.get('name') or customer_id))}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


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
    
    async with async_session_maker() as session:
        updated = await ProductService.update_price(session, int(data["product_id"]), int(message.text))

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
    
    async with async_session_maker() as session:
        try:
            deleted = await ProductService.delete(session, product_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    if not deleted:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await state.update_data(delete_product_confirmation={})
    await callback.message.delete()
    await callback.answer("Удалено")
