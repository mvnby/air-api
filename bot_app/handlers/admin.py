from io import BytesIO
from html import escape
import os

from aiogram import Router, types, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from core.database import async_session_maker
from services.product_service import ProductService
from services.staff_user_service import StaffUserService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from ..config import bot
from ..states import ShopState

router = Router()


async def _is_admin_user(user_id: int | None) -> bool:
    async with async_session_maker() as session:
        return await StaffUserService.is_active_owner_admin_telegram_user(session, user_id)


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


async def _download_telegram_file(file_id: str) -> bytes:
    buffer = BytesIO()
    await bot.download(file_id, destination=buffer)
    return buffer.getvalue()


async def _handle_requisites_file(
    message: types.Message,
    *,
    file_id: str,
    filename: str,
    mime_type: str,
):
    if not await _is_admin_user(message.from_user.id if message.from_user else None):
        await message.answer("Распознавание реквизитов доступно только администраторам.")
        return

    progress = await message.answer("Распознаю реквизиты…")
    try:
        content = await _download_telegram_file(file_id)
        async with async_session_maker() as session:
            data = await CustomerRequisitesRecognitionService.recognize_bytes(
                session,
                content=content,
                filename=filename,
                mime_type=mime_type,
                source="telegram",
                telegram_user_id=message.from_user.id if message.from_user else None,
                telegram_chat_id=message.chat.id if message.chat else None,
                telegram_message_id=message.message_id,
            )
    except Exception as exc:
        await progress.edit_text(f"❌ Не удалось распознать реквизиты: {escape(str(exc))}")
        return

    await progress.edit_text(_preview_text(data), reply_markup=_preview_keyboard(data), parse_mode="HTML")


@router.message(F.photo)
async def recognize_requisites_photo(message: types.Message):
    if not message.photo:
        return
    photo = message.photo[-1]
    await _handle_requisites_file(
        message,
        file_id=photo.file_id,
        filename=f"telegram-photo-{message.message_id}.jpg",
        mime_type="image/jpeg",
    )


@router.message(F.document)
async def recognize_requisites_document(message: types.Message):
    document = message.document
    if not document:
        return
    mime_type = document.mime_type or ""
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        return
    await _handle_requisites_file(
        message,
        file_id=document.file_id,
        filename=document.file_name or f"telegram-document-{message.message_id}",
        mime_type=mime_type,
    )


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

@router.callback_query(F.data.startswith("del_confirm_"))
async def delete_item(callback: CallbackQuery):
    if not await _is_admin_user(callback.from_user.id):
        return
    
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
