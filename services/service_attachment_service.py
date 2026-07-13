"""Business logic for private order and equipment attachments."""

from __future__ import annotations

import asyncio
import hmac
import io
import logging
import mimetypes
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import and_, func, select

from core.config import settings
from models import (
    CustomerEquipment,
    EquipmentAttachmentLink,
    EquipmentComponent,
    Order,
    OrderAttachmentLink,
    OrderWorkStage,
    ServiceAttachment,
)
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    extension_for,
    get_private_attachment_storage,
    sha256_bytes,
)


logger = logging.getLogger(__name__)


class ServiceAttachmentService:
    CATEGORIES = {
        "nameplate",
        "before_work",
        "after_work",
        "installation_result",
        "defect",
        "service",
        "document",
        "other",
    }
    SAFE_MIME_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
    }

    @staticmethod
    def normalize_category(value: str | None) -> str:
        normalized = str(value or "other").strip().lower()
        if normalized not in ServiceAttachmentService.CATEGORIES:
            raise ValueError(f"Unsupported attachment category: {normalized}")
        return normalized

    @staticmethod
    def _normalize_mime_type(value: str | None, filename: str) -> str:
        supplied = str(value or "").split(";", 1)[0].strip().lower()
        guessed = mimetypes.guess_type(filename or "")[0] or ""
        mime_type = supplied or guessed or "application/octet-stream"
        if mime_type not in ServiceAttachmentService.SAFE_MIME_TYPES:
            raise ValueError(f"Unsupported attachment type: {mime_type}")
        return mime_type

    @staticmethod
    def file_kind(mime_type: str) -> str:
        if mime_type.startswith("image/"):
            return "image"
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("text/") or "word" in mime_type or "excel" in mime_type or "sheet" in mime_type:
            return "document"
        return "other"

    @staticmethod
    def _clean_text(value: Any, *, limit: int | None = None) -> str | None:
        cleaned = " ".join(str(value or "").split()).strip()
        if not cleaned:
            return None
        return cleaned[:limit] if limit else cleaned

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed

    @staticmethod
    def _image_preview(content: bytes) -> tuple[bytes, str] | None:
        try:
            with Image.open(io.BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((720, 720), Image.Resampling.LANCZOS)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=82, method=6, exif=b"")
                return output.getvalue(), "image/webp"
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            logger.info("Attachment preview could not be generated", exc_info=True)
            return None

    @classmethod
    async def create_and_link_order_attachment(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        content: bytes,
        filename: str,
        mime_type: str | None,
        category: str = "other",
        caption: str | None = None,
        source: str = "manager",
        created_by: str | None = None,
        work_stage_id: int | None = None,
        equipment_id: int | None = None,
        component_id: int | None = None,
        transcript: str | None = None,
        captured_at: datetime | None = None,
        telegram_meta: dict[str, Any] | None = None,
        storage: PrivateAttachmentStorage | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Attachment is empty")
        if len(content) > int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES):
            raise ValueError("Attachment exceeds the configured size limit")
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")
        if work_stage_id is not None:
            stage = await session.get(OrderWorkStage, work_stage_id)
            if not stage or int(stage.order_id) != order_id:
                raise ValueError("Work stage does not belong to this order")
        equipment = None
        if equipment_id is not None:
            equipment = await session.get(CustomerEquipment, equipment_id)
            if not equipment:
                raise ValueError("Equipment not found")
            if order.customer_id is None or int(equipment.customer_id) != int(order.customer_id):
                raise ValueError("Equipment does not belong to the order customer")
            if (
                order.customer_branch_id is not None
                and equipment.customer_branch_id is not None
                and int(order.customer_branch_id) != int(equipment.customer_branch_id)
            ):
                raise ValueError("Equipment does not belong to the order branch")
        if component_id is not None:
            component = await session.get(EquipmentComponent, component_id)
            if not component or equipment_id is None or int(component.equipment_id) != equipment_id:
                raise ValueError("Equipment component does not belong to this equipment")

        clean_filename = cls._clean_text(filename, limit=255) or "attachment"
        normalized_mime = cls._normalize_mime_type(mime_type, clean_filename)
        normalized_category = cls.normalize_category(category)
        digest = sha256_bytes(content)
        existing_result = await session.execute(
            select(ServiceAttachment).where(ServiceAttachment.content_hash == digest)
        )
        attachment = existing_result.scalars().first()
        selected_storage = storage or get_private_attachment_storage()

        if attachment is None:
            original = await selected_storage.save(
                content=content,
                content_hash=digest,
                extension=extension_for(clean_filename, normalized_mime),
                content_type=normalized_mime,
                variant="original",
            )
            preview_key = None
            preview_mime = None
            if normalized_mime.startswith("image/"):
                preview = await asyncio.to_thread(cls._image_preview, content)
                if preview:
                    preview_content, preview_mime = preview
                    stored_preview = await selected_storage.save(
                        content=preview_content,
                        content_hash=digest,
                        extension="webp",
                        content_type=preview_mime,
                        variant="preview",
                    )
                    preview_key = stored_preview.storage_key

            telegram_meta = telegram_meta or {}
            attachment = ServiceAttachment(
                file_kind=cls.file_kind(normalized_mime),
                original_filename=clean_filename,
                mime_type=normalized_mime,
                size_bytes=len(content),
                content_hash=digest,
                storage_provider=original.provider,
                storage_key=original.storage_key,
                preview_storage_key=preview_key,
                preview_mime_type=preview_mime,
                source=source,
                processing_status="ready",
                transcript=cls._clean_text(transcript),
                source_meta=dict(telegram_meta.get("source_meta") or {}),
                telegram_file_id=cls._clean_text(telegram_meta.get("file_id"), limit=255),
                telegram_chat_id=telegram_meta.get("chat_id"),
                telegram_message_id=telegram_meta.get("message_id"),
                telegram_user_id=telegram_meta.get("user_id"),
                captured_at=captured_at,
                created_by=created_by,
            )
            try:
                async with session.begin_nested():
                    session.add(attachment)
                    await session.flush()
            except IntegrityError:
                existing_result = await session.execute(
                    select(ServiceAttachment).where(ServiceAttachment.content_hash == digest)
                )
                attachment = existing_result.scalars().one()
        elif attachment.archived_at is not None:
            attachment.archived_at = None
            attachment.updated_at = datetime.now()
            session.add(attachment)
            await session.flush()

        link_result = await session.execute(
            select(OrderAttachmentLink).where(
                OrderAttachmentLink.order_id == order_id,
                OrderAttachmentLink.attachment_id == int(attachment.id or 0),
            )
        )
        link = link_result.scalars().first()
        if link is None:
            link = OrderAttachmentLink(
                order_id=order_id,
                attachment_id=int(attachment.id or 0),
                work_stage_id=work_stage_id,
                category=normalized_category,
                caption=cls._clean_text(caption),
            )
        else:
            link.archived_at = None
            link.work_stage_id = work_stage_id or link.work_stage_id
            link.category = normalized_category
            link.caption = cls._clean_text(caption) or link.caption
        session.add(link)

        if equipment is not None:
            equipment_link_result = await session.execute(
                select(EquipmentAttachmentLink).where(
                    EquipmentAttachmentLink.equipment_id == int(equipment.id or 0),
                    EquipmentAttachmentLink.attachment_id == int(attachment.id or 0),
                )
            )
            equipment_link = equipment_link_result.scalars().first()
            if equipment_link is None:
                equipment_link = EquipmentAttachmentLink(
                    equipment_id=int(equipment.id or 0),
                    attachment_id=int(attachment.id or 0),
                    component_id=component_id,
                    category=normalized_category,
                    caption=cls._clean_text(caption),
                )
            else:
                equipment_link.archived_at = None
                equipment_link.component_id = component_id or equipment_link.component_id
                equipment_link.category = normalized_category
                equipment_link.caption = cls._clean_text(caption) or equipment_link.caption
            session.add(equipment_link)

        await session.commit()
        await session.refresh(attachment)
        return cls.to_item(attachment, link=link, equipment_id=equipment_id, component_id=component_id)

    @classmethod
    def to_item(
        cls,
        attachment: ServiceAttachment,
        *,
        link: OrderAttachmentLink | EquipmentAttachmentLink | None = None,
        equipment_id: int | None = None,
        component_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": int(attachment.id or 0),
            "legacy_key": None,
            "legacy": False,
            "file_kind": attachment.file_kind,
            "category": link.category if link else "other",
            "filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
            "size_bytes": int(attachment.size_bytes or 0),
            "caption": link.caption if link else None,
            "transcript": attachment.transcript,
            "source": attachment.source,
            "processing_status": attachment.processing_status,
            "processing_error": attachment.processing_error,
            "captured_at": attachment.captured_at,
            "created_at": attachment.created_at,
            "preview_available": bool(attachment.preview_storage_key),
            "equipment_id": equipment_id,
            "component_id": component_id,
        }

    @classmethod
    def _legacy_items(cls, order: Order, normalized_file_ids: set[str]) -> list[dict[str, Any]]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        raw_items = meta.get("telegram_attachments")
        if not isinstance(raw_items, list):
            return []
        result: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                continue
            file_id = str(raw.get("file_id") or "").strip()
            if file_id and file_id in normalized_file_ids:
                continue
            mime_type = str(raw.get("mime_type") or "application/octet-stream")
            result.append(
                {
                    "id": None,
                    "legacy_key": f"telegram:{index}:{file_id or 'unknown'}",
                    "legacy": True,
                    "file_kind": cls.file_kind(mime_type),
                    "category": str(raw.get("purpose") or "other"),
                    "filename": str(raw.get("filename") or f"Telegram файл {index + 1}"),
                    "mime_type": mime_type,
                    "size_bytes": int(raw.get("size_bytes") or 0),
                    "caption": None,
                    "transcript": None,
                    "source": "telegram_bot",
                    "processing_status": "migration_required",
                    "processing_error": "Файл найден в старых данных и ожидает безопасного переноса.",
                    "captured_at": cls._parse_datetime(raw.get("attached_at")),
                    "created_at": cls._parse_datetime(raw.get("attached_at")) or order.created_at,
                    "preview_available": False,
                    "equipment_id": None,
                    "component_id": None,
                }
            )
        return result

    @classmethod
    async def list_order_attachments(cls, session: AsyncSession, *, order_id: int) -> dict[str, Any] | None:
        order = await session.get(Order, order_id)
        if not order:
            return None
        result = await session.execute(
            select(ServiceAttachment, OrderAttachmentLink, EquipmentAttachmentLink)
            .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
            .outerjoin(
                EquipmentAttachmentLink,
                and_(
                    EquipmentAttachmentLink.attachment_id == ServiceAttachment.id,
                    EquipmentAttachmentLink.archived_at.is_(None),
                ),
            )
            .where(
                OrderAttachmentLink.order_id == order_id,
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            )
            .order_by(ServiceAttachment.captured_at.desc().nullslast(), ServiceAttachment.created_at.desc())
        )
        rows = result.all()
        items = []
        seen_attachment_ids: set[int] = set()
        for attachment, link, equipment_link in rows:
            attachment_id = int(attachment.id or 0)
            if attachment_id in seen_attachment_ids:
                continue
            seen_attachment_ids.add(attachment_id)
            items.append(
                cls.to_item(
                    attachment,
                    link=link,
                    equipment_id=equipment_link.equipment_id if equipment_link else None,
                    component_id=equipment_link.component_id if equipment_link else None,
                )
            )
        normalized_file_ids = {
            str(attachment.telegram_file_id)
            for attachment, _, _ in rows
            if attachment.telegram_file_id
        }
        items.extend(cls._legacy_items(order, normalized_file_ids))
        return {"items": items, "total": len(items)}

    @classmethod
    async def list_equipment_attachments(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
    ) -> dict[str, Any] | None:
        equipment = await session.get(CustomerEquipment, equipment_id)
        if not equipment:
            return None
        result = await session.execute(
            select(ServiceAttachment, EquipmentAttachmentLink)
            .join(EquipmentAttachmentLink, EquipmentAttachmentLink.attachment_id == ServiceAttachment.id)
            .where(
                EquipmentAttachmentLink.equipment_id == equipment_id,
                EquipmentAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            )
            .order_by(ServiceAttachment.captured_at.desc().nullslast(), ServiceAttachment.created_at.desc())
        )
        items = [
            cls.to_item(
                attachment,
                link=equipment_link,
                equipment_id=equipment_id,
                component_id=equipment_link.component_id,
            )
            for attachment, equipment_link in result.all()
        ]
        return {"items": items, "total": len(items)}

    @classmethod
    async def order_attachment_count(cls, session: AsyncSession, *, order: Order) -> int:
        db_count = await session.scalar(
            select(func.count(OrderAttachmentLink.id))
            .join(ServiceAttachment, ServiceAttachment.id == OrderAttachmentLink.attachment_id)
            .where(
                OrderAttachmentLink.order_id == int(order.id or 0),
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            )
        )
        normalized_result = await session.execute(
            select(ServiceAttachment.telegram_file_id)
            .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
            .where(
                OrderAttachmentLink.order_id == int(order.id or 0),
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.telegram_file_id.is_not(None),
            )
        )
        normalized_ids = {str(item) for item in normalized_result.scalars().all() if item}
        return int(db_count or 0) + len(cls._legacy_items(order, normalized_ids))

    @classmethod
    async def update_attachment(
        cls,
        session: AsyncSession,
        *,
        attachment_id: int,
        order_id: int | None,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return None
        link = None
        if order_id is not None:
            link_result = await session.execute(
                select(OrderAttachmentLink).where(
                    OrderAttachmentLink.order_id == order_id,
                    OrderAttachmentLink.attachment_id == attachment_id,
                    OrderAttachmentLink.archived_at.is_(None),
                )
            )
            link = link_result.scalars().first()
            if not link:
                raise ValueError("Attachment does not belong to this order")
        if "category" in payload:
            if not link:
                raise ValueError("order_id is required to change attachment category")
            link.category = cls.normalize_category(payload.get("category"))
        if "caption" in payload:
            if not link:
                raise ValueError("order_id is required to change attachment caption")
            link.caption = cls._clean_text(payload.get("caption"))
        if "transcript" in payload:
            attachment.transcript = cls._clean_text(payload.get("transcript"))
        equipment_id_for_response: int | None = None
        component_id_for_response: int | None = None
        if "equipment_id" in payload:
            if order_id is None:
                raise ValueError("order_id is required to change equipment link")
            equipment_id = payload.get("equipment_id")
            component_id = payload.get("component_id")
            equipment_links_result = await session.execute(
                select(EquipmentAttachmentLink).where(
                    EquipmentAttachmentLink.attachment_id == attachment_id,
                    EquipmentAttachmentLink.archived_at.is_(None),
                )
            )
            equipment_links = list(equipment_links_result.scalars().all())
            if equipment_id is None:
                for equipment_link in equipment_links:
                    equipment_link.archived_at = datetime.now()
                    session.add(equipment_link)
            else:
                order = await session.get(Order, order_id)
                equipment = await session.get(CustomerEquipment, int(equipment_id))
                if not order or not equipment:
                    raise ValueError("Order or equipment not found")
                if order.customer_id is None or int(order.customer_id) != int(equipment.customer_id):
                    raise ValueError("Equipment does not belong to the order customer")
                if (
                    order.customer_branch_id is not None
                    and equipment.customer_branch_id is not None
                    and int(order.customer_branch_id) != int(equipment.customer_branch_id)
                ):
                    raise ValueError("Equipment does not belong to the order branch")
                if component_id is not None:
                    component = await session.get(EquipmentComponent, int(component_id))
                    if not component or int(component.equipment_id) != int(equipment_id):
                        raise ValueError("Equipment component does not belong to this equipment")
                target = next(
                    (item for item in equipment_links if int(item.equipment_id) == int(equipment_id)),
                    None,
                )
                if target is None:
                    target = EquipmentAttachmentLink(
                        equipment_id=int(equipment_id),
                        attachment_id=attachment_id,
                    )
                target.archived_at = None
                target.component_id = int(component_id) if component_id is not None else None
                target.category = link.category if link else "other"
                target.caption = link.caption if link else None
                session.add(target)
                for equipment_link in equipment_links:
                    if equipment_link is target:
                        continue
                    equipment_link.archived_at = datetime.now()
                    session.add(equipment_link)

        active_equipment_link_result = await session.execute(
            select(EquipmentAttachmentLink).where(
                EquipmentAttachmentLink.attachment_id == attachment_id,
                EquipmentAttachmentLink.archived_at.is_(None),
            )
        )
        active_equipment_link = active_equipment_link_result.scalars().first()
        if active_equipment_link:
            if link and ("category" in payload or "caption" in payload):
                active_equipment_link.category = link.category
                active_equipment_link.caption = link.caption
                session.add(active_equipment_link)
            equipment_id_for_response = int(active_equipment_link.equipment_id)
            component_id_for_response = active_equipment_link.component_id
        attachment.updated_at = datetime.now()
        session.add(attachment)
        if link:
            session.add(link)
        await session.commit()
        await session.refresh(attachment)
        return cls.to_item(
            attachment,
            link=link,
            equipment_id=equipment_id_for_response,
            component_id=component_id_for_response,
        )

    @staticmethod
    async def archive_attachment(
        session: AsyncSession,
        *,
        attachment_id: int,
        order_id: int | None = None,
    ) -> bool:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return False
        if order_id is not None:
            link_result = await session.execute(
                select(OrderAttachmentLink).where(
                    OrderAttachmentLink.order_id == order_id,
                    OrderAttachmentLink.attachment_id == attachment_id,
                    OrderAttachmentLink.archived_at.is_(None),
                )
            )
            link = link_result.scalars().first()
            if not link:
                return False
            link.archived_at = datetime.now()
            session.add(link)
        else:
            attachment.archived_at = datetime.now()
            attachment.updated_at = datetime.now()
            session.add(attachment)
        await session.commit()
        return True

    @staticmethod
    def _local_signature(attachment_id: int, variant: str, expires: int, download: bool) -> str:
        message = f"{attachment_id}:{variant}:{expires}:{int(download)}".encode()
        return hmac.new(settings.SECRET_KEY.encode(), message, sha256).hexdigest()

    @classmethod
    def validate_local_signature(
        cls,
        *,
        attachment_id: int,
        variant: str,
        expires: int,
        download: bool,
        signature: str,
    ) -> bool:
        if int(expires) < int(datetime.now().timestamp()):
            return False
        expected = cls._local_signature(attachment_id, variant, expires, download)
        return hmac.compare_digest(expected, str(signature or ""))

    @classmethod
    async def get_access(
        cls,
        session: AsyncSession,
        *,
        attachment_id: int,
        variant: str,
        download: bool,
        storage: PrivateAttachmentStorage | None = None,
    ) -> dict[str, Any] | None:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return None
        normalized_variant = "preview" if variant == "preview" and attachment.preview_storage_key else "original"
        storage_key = attachment.preview_storage_key if normalized_variant == "preview" else attachment.storage_key
        if not storage_key:
            raise FileNotFoundError("Attachment source is not available")
        ttl = max(30, min(int(settings.SERVICE_ATTACHMENT_ACCESS_TTL_SECONDS), 3600))
        selected_storage = storage or get_private_attachment_storage(attachment.storage_provider)
        expires_at = datetime.now() + timedelta(seconds=ttl)
        direct_url = await selected_storage.presign(
            storage_key,
            expires_seconds=ttl,
            download_name=attachment.original_filename if download else None,
        )
        if direct_url:
            return {"url": direct_url, "expires_at": expires_at, "variant": normalized_variant}
        expires = int(expires_at.timestamp())
        signature = cls._local_signature(attachment_id, normalized_variant, expires, download)
        filename = quote(attachment.original_filename)
        url = (
            f"/api/manager/service-attachments/{attachment_id}/content"
            f"?variant={normalized_variant}&expires={expires}&download={str(download).lower()}"
            f"&signature={signature}&filename={filename}"
        )
        return {"url": url, "expires_at": expires_at, "variant": normalized_variant}

    @staticmethod
    async def read_variant(
        session: AsyncSession,
        *,
        attachment_id: int,
        variant: str,
        storage: PrivateAttachmentStorage | None = None,
    ) -> tuple[ServiceAttachment, bytes, str]:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            raise FileNotFoundError("Attachment not found")
        normalized_variant = "preview" if variant == "preview" and attachment.preview_storage_key else "original"
        key = attachment.preview_storage_key if normalized_variant == "preview" else attachment.storage_key
        if not key:
            raise FileNotFoundError("Attachment source is not available")
        selected_storage = storage or get_private_attachment_storage(attachment.storage_provider)
        content = await selected_storage.read(key)
        mime_type = attachment.preview_mime_type if normalized_variant == "preview" else attachment.mime_type
        return attachment, content, mime_type or "application/octet-stream"
