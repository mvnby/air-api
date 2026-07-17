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
    unit_label = WARRANTY_UNIT_LABELS.get(unit_type, "блок")
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
    for field in REPAIR_FIELDS:
        label = REPAIR_FIELD_LABELS.get(field, field)
        value = extracted.get(field)
        if value:
            lines.append(f"<b>{escape(label)}:</b> {escape(str(value))}")
    lines.extend(_serial_candidate_preview_lines(extracted, validation_flags))
    lines.extend(_serial_details_preview_lines(validation_flags))

    if applied:
        lines.extend(["", "<b>Будет записано:</b>"])
        lines.extend(
            f"• {escape(REPAIR_FIELD_LABELS.get(field, field))}: {escape(str(value))}"
            for field, value in applied.items()
        )
    if skipped:
        lines.extend(["", "<b>Уже было заполнено таким же значением:</b>"])
        lines.extend(
            f"• {escape(REPAIR_FIELD_LABELS.get(field, field))}: {escape(str(value))}"
            for field, value in skipped.items()
        )
    if conflicts:
        lines.extend(["", "<b>Конфликты, не перезапишу автоматически:</b>"])
        for field, values in conflicts.items():
            label = REPAIR_FIELD_LABELS.get(field, field)
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
    unit_label = merge_preview.get("unit_label") or WARRANTY_UNIT_LABELS.get(str(data.get("unit_type")), "блок")

    lines = [f"<b>Распознал шильдик для гарантии: {escape(str(unit_label))}.</b>", ""]
    fields = {
        "brand": extracted.get("equipment_brand"),
        "model": extracted.get("equipment_model"),
        "serial": extracted.get("equipment_serial_number"),
        "refrigerant_type": extracted.get("refrigerant_type"),
    }
    for field, value in fields.items():
        if value:
            lines.append(f"<b>{escape(WARRANTY_FIELD_LABELS.get(field, field))}:</b> {escape(str(value))}")
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
            lines.append(f"• {escape(WARRANTY_FIELD_LABELS.get(field, field))}: {escape(str(value))}")
        for field, value in equipment_applied.items():
            lines.append(f"• карточка: {escape(WARRANTY_FIELD_LABELS.get(field, field))}: {escape(str(value))}")
    if skipped:
        lines.extend(["", "<b>Уже заполнено таким же значением:</b>"])
        for field in skipped.keys():
            lines.append(f"• {escape(WARRANTY_FIELD_LABELS.get(field, field))}")
    if conflicts:
        lines.extend(["", "<b>Конфликты, не перезапишу автоматически:</b>"])
        for field, values in conflicts.items():
            existing = values.get("existing") if isinstance(values, dict) else ""
            candidate = values.get("candidate") if isinstance(values, dict) else ""
            lines.append(
                f"• {escape(WARRANTY_FIELD_LABELS.get(field, field))}: "
                f"сейчас {escape(str(existing))}, распознано {escape(str(candidate))}"
            )
    if warnings:
        lines.extend(["", "<b>Предупреждения:</b>"])
        lines.extend(f"• {escape(str(message))}" for message in warnings.values())
    return "\n".join(lines)


def _file_too_large_message(max_bytes: int = BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES) -> str:
    max_mb = max_bytes / (1024 * 1024)
    return f"Файл слишком большой. Максимум {max_mb:g} МБ."


def _normalize_file_size(value: object) -> int | None:
    try:
        size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


async def _download_telegram_file(file_id: str, *, expected_size: int | None = None) -> bytes:
    max_bytes = BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES
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
        data = (
            await get_bot_api_gateway().recognize_customer_requisites_file(
                telegram_id=int(telegram_user_id or 0),
                content=content,
                filename=filename,
                mime_type=mime_type,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
        ).model_dump(mode="json")
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
        data = (
            await get_bot_api_gateway().recognize_customer_requisites_text(
                telegram_id=int(telegram_user_id or 0),
                text=text,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
        ).model_dump(mode="json")
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
    if normalized_size is not None and normalized_size > BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES:
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



__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
