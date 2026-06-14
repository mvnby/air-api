from datetime import datetime
from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Order, OrderInstaller, OrderStatus, OrderWorkStage, StaffUser
from services.staff_user_service import StaffUserService


class BotOrderAttachmentService:
    TELEGRAM_ATTACHMENTS_META_KEY = "telegram_attachments"
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
    ) -> dict[str, Any]:
        return {
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

    @staticmethod
    def _comment_line(entry: dict[str, Any], attached_at: datetime) -> str:
        filename = BotOrderAttachmentService._clean_filename(entry.get("filename"))
        kind = "Фото" if entry.get("kind") == "photo" else "PDF" if entry.get("kind") == "pdf" else "Документ"
        return (
            f"[Telegram attachment {attached_at.strftime('%d.%m.%Y %H:%M')}] "
            f"{kind}: {filename}; file_id={entry.get('file_id')}"
        )

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
    ) -> dict[str, Any] | None:
        stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.customer))
        result = await session.execute(stmt)
        order = result.scalars().first()
        if not order:
            return None

        attached_at = datetime.now()
        entry = cls._build_entry(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            attached_at=attached_at,
        )

        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        raw_attachments = meta.get(cls.TELEGRAM_ATTACHMENTS_META_KEY)
        attachments = list(raw_attachments) if isinstance(raw_attachments, list) else []
        already_attached = any(isinstance(item, dict) and item.get("file_id") == file_id for item in attachments)
        if not already_attached:
            attachments.append(entry)
            meta[cls.TELEGRAM_ATTACHMENTS_META_KEY] = attachments
            order.technical_meta = meta
            order.comment = cls._append_comment(order.comment, cls._comment_line(entry, attached_at))
            flag_modified(order, "technical_meta")
            session.add(order)
            await session.commit()
            await session.refresh(order)

        data = cls._map_order(order)
        data["attachment"] = entry
        data["already_attached"] = already_attached
        return data
