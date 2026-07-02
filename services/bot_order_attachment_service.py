from datetime import datetime
import mimetypes
from pathlib import Path
from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Order, OrderInstaller, OrderStatus, OrderWorkStage, StaffUser
from services.general_media_storage_service import (
    StoredGeneralMediaObject,
    get_general_media_storage,
)
from services.staff_user_service import StaffUserService


class BotOrderAttachmentService:
    TELEGRAM_ATTACHMENTS_META_KEY = "telegram_attachments"
    PERSISTED_ENTRY_KEYS = {
        "source",
        "file_id",
        "filename",
        "mime_type",
        "kind",
        "telegram_user_id",
        "telegram_chat_id",
        "telegram_message_id",
        "attached_at",
        "purpose",
        "url",
        "storage_provider",
        "storage_path",
        "content_hash",
        "size_bytes",
    }
    ACTIVE_STATUSES = {
        OrderStatus.NEW_LEAD,
        OrderStatus.NEGOTIATION,
        OrderStatus.EXECUTION,
    }

    @staticmethod
    def _clean_filename(value: Any) -> str:
        return " ".join(str(value or "telegram-file").split())[:160] or "telegram-file"

    @staticmethod
    def _file_kind(mime_type: str | None) -> str:
        if str(mime_type or "").startswith("image/"):
            return "photo"
        if str(mime_type or "") == "application/pdf":
            return "pdf"
        return "document"

    @staticmethod
    def _extension_from_filename_or_mime(filename: str, mime_type: str | None) -> str:
        suffix = Path(str(filename or "")).suffix.lower().lstrip(".")
        if suffix and "/" not in suffix and "\\" not in suffix:
            return "jpg" if suffix == "jpeg" else suffix
        guessed = mimetypes.guess_extension(str(mime_type or "").split(";", 1)[0].strip())
        if guessed:
            normalized = guessed.lower().lstrip(".")
            return "jpg" if normalized in {"jpeg", "jpe"} else normalized
        return "bin"

    @classmethod
    def _build_entry(
        cls,
        *,
        file_id: str,
        filename: str,
        mime_type: str | None,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        attached_at: datetime,
        url: str | None = None,
        storage_provider: str | None = None,
        storage_path: str | None = None,
        content_hash: str | None = None,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        entry = {
            "source": "telegram_bot",
            "file_id": file_id,
            "filename": cls._clean_filename(filename),
            "mime_type": mime_type or "application/octet-stream",
            "kind": cls._file_kind(mime_type),
            "telegram_user_id": telegram_user_id,
            "telegram_chat_id": telegram_chat_id,
            "telegram_message_id": telegram_message_id,
            "attached_at": attached_at.isoformat(timespec="seconds"),
        }
        if url:
            entry["url"] = url
        if storage_provider:
            entry["storage_provider"] = storage_provider
        if storage_path:
            entry["storage_path"] = storage_path
        if content_hash:
            entry["content_hash"] = content_hash
        if size_bytes is not None:
            entry["size_bytes"] = size_bytes
        return entry

    @classmethod
    def persisted_entry(cls, entry: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in entry.items() if key in cls.PERSISTED_ENTRY_KEYS}

    @classmethod
    def upsert_telegram_attachment(
        cls,
        meta: dict[str, Any],
        entry: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], bool]:
        persisted = cls.persisted_entry(entry)
        raw_attachments = meta.get(cls.TELEGRAM_ATTACHMENTS_META_KEY)
        attachments = list(raw_attachments) if isinstance(raw_attachments, list) else []
        file_id = persisted.get("file_id")
        purpose = persisted.get("purpose")
        existing_index = next(
            (
                index
                for index, item in enumerate(attachments)
                if isinstance(item, dict)
                and item.get("file_id") == file_id
                and item.get("purpose") == purpose
            ),
            None,
        )

        if existing_index is None:
            attachments.append(persisted)
            already_attached = False
        else:
            current = dict(attachments[existing_index])
            current.update(persisted)
            attachments[existing_index] = current
            already_attached = True

        meta[cls.TELEGRAM_ATTACHMENTS_META_KEY] = attachments
        return attachments, already_attached

    @staticmethod
    def _comment_line(entry: dict[str, Any], attached_at: datetime) -> str:
        filename = BotOrderAttachmentService._clean_filename(entry.get("filename"))
        kind = "Фото" if entry.get("kind") == "photo" else "PDF" if entry.get("kind") == "pdf" else "Документ"
        line = (
            f"[Telegram attachment {attached_at.strftime('%d.%m.%Y %H:%M')}] "
            f"{kind}: {filename}; file_id={entry.get('file_id')}"
        )
        if entry.get("url"):
            line = f"{line}; url={entry.get('url')}"
        return line

    @staticmethod
    def _append_comment(existing: str | None, line: str) -> str:
        current = (existing or "").strip()
        if line in current:
            return current
        return f"{current}\n\n{line}".strip() if current else line

    @staticmethod
    def _map_order(order: Order) -> dict[str, Any]:
        customer = getattr(order, "customer", None)
        return {
            "id": int(order.id or 0),
            "title": order.title,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "customer_name": getattr(customer, "name", None) if customer else None,
            "customer_phone": getattr(customer, "phone", None) if customer else None,
            "address": order.delivery_address,
            "updated_at": order.updated_at,
            "created_at": order.created_at,
        }

    @classmethod
    async def list_recent_orders(cls, session: AsyncSession, *, limit: int = 5) -> list[dict[str, Any]]:
        stmt = (
            select(Order)
            .where(Order.status.in_(list(cls.ACTIVE_STATUSES)))
            .options(selectinload(Order.customer))
            .order_by(Order.updated_at.desc(), Order.created_at.desc(), Order.id.desc())
            .limit(max(1, min(limit, 10)))
        )
        result = await session.execute(stmt)
        return [cls._map_order(order) for order in result.scalars().all()]

    @classmethod
    async def can_attach_to_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        telegram_user_id: int | str | None,
        can_attach_any: bool = False,
    ) -> bool:
        if can_attach_any:
            return True

        try:
            normalized_telegram_id = int(telegram_user_id) if telegram_user_id is not None else 0
        except (TypeError, ValueError):
            return False
        if not normalized_telegram_id:
            return False

        staff_result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .where(StaffUser.status == StaffUserService.STATUS_ACTIVE)
            .order_by(StaffUser.id.asc())
        )
        staff = staff_result.scalars().first()
        installer_id = getattr(staff, "legacy_installer_id", None)
        if not installer_id:
            return False

        stage_result = await session.execute(
            select(OrderWorkStage.id)
            .where(OrderWorkStage.order_id == order_id)
            .where(OrderWorkStage.installer_id == int(installer_id))
            .limit(1)
        )
        if stage_result.first():
            return True

        legacy_result = await session.execute(
            select(OrderInstaller.order_id)
            .where(OrderInstaller.order_id == order_id)
            .where(OrderInstaller.installer_id == int(installer_id))
            .limit(1)
        )
        return legacy_result.first() is not None

    @classmethod
    async def attach_to_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        file_id: str,
        filename: str,
        mime_type: str | None,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        content: bytes | None = None,
    ) -> dict[str, Any] | None:
        stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.customer))
        result = await session.execute(stmt)
        order = result.scalars().first()
        if not order:
            return None

        attached_at = datetime.now()
        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        raw_attachments = meta.get(cls.TELEGRAM_ATTACHMENTS_META_KEY)
        attachments = list(raw_attachments) if isinstance(raw_attachments, list) else []
        existing_index = next(
            (
                index
                for index, item in enumerate(attachments)
                if isinstance(item, dict) and item.get("file_id") == file_id
            ),
            None,
        )
        existing_entry = attachments[existing_index] if existing_index is not None else None
        already_attached = isinstance(existing_entry, dict)
        storage_meta: dict[str, Any] = {}
        if content and (not already_attached or not existing_entry.get("url")):
            stored = await cls.store_attachment_content(
                order_id=order_id,
                content=content,
                filename=filename,
                mime_type=mime_type,
            )
            storage_meta = {
                "url": stored.url,
                "storage_provider": stored.storage_provider,
                "storage_path": stored.path,
                "content_hash": stored.content_hash,
                "size_bytes": stored.size_bytes,
            }

        if already_attached:
            entry = dict(existing_entry)
            entry.update(storage_meta)
        else:
            entry = cls._build_entry(
                file_id=file_id,
                filename=filename,
                mime_type=mime_type,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
                attached_at=attached_at,
                **storage_meta,
            )

        if not already_attached or storage_meta:
            attachments, _ = cls.upsert_telegram_attachment(meta, entry)
            meta[cls.TELEGRAM_ATTACHMENTS_META_KEY] = attachments
            order.technical_meta = meta
            if not already_attached:
                order.comment = cls._append_comment(order.comment, cls._comment_line(entry, attached_at))
            flag_modified(order, "technical_meta")
            session.add(order)
            await session.commit()
            await session.refresh(order)

        data = cls._map_order(order)
        data["attachment"] = entry
        data["already_attached"] = already_attached
        return data

    @classmethod
    async def store_attachment_content(
        cls,
        *,
        order_id: int,
        content: bytes,
        filename: str,
        mime_type: str | None,
    ) -> StoredGeneralMediaObject:
        storage = get_general_media_storage()
        return await storage.save_media(
            content=content,
            namespace=f"orders/{order_id}/telegram",
            variant_type=cls._file_kind(mime_type),
            extension=cls._extension_from_filename_or_mime(filename, mime_type),
            content_type=mime_type or "application/octet-stream",
        )
