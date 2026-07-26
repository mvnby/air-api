"""Presentation and image helpers for private service attachments."""

from __future__ import annotations

import io
import hashlib
import logging
from datetime import datetime
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from models import EquipmentAttachmentLink, Order, OrderAttachmentLink, ServiceAttachment


logger = logging.getLogger(__name__)


def legacy_attachment_source_key(order_id: int, raw: dict[str, Any]) -> str:
    file_id = " ".join(str(raw.get("file_id") or "").split()).strip()
    url = " ".join(str(raw.get("url") or "").split()).strip()
    filename = " ".join(str(raw.get("filename") or "telegram-file").split()).strip()
    purpose = " ".join(str(raw.get("purpose") or "other").split()).strip()
    known_categories = {
        "nameplate",
        "before_work",
        "after_work",
        "installation_result",
        "installation_indoor",
        "installation_outdoor",
        "installation_route",
        "installation_facade",
        "installation_power",
        "defect",
        "service",
        "document",
        "other",
    }
    category = "nameplate" if "nameplate" in purpose else purpose if purpose in known_categories else "other"
    source_ref = file_id or url or filename
    chat_id = raw.get("telegram_chat_id")
    message_id = raw.get("telegram_message_id")
    if chat_id is not None and message_id is not None:
        source_ref = f"telegram:{int(chat_id)}:{int(message_id)}"
    payload = "\x1f".join((str(order_id), source_ref, category))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def attachment_file_kind(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("text/") or "word" in mime_type or "excel" in mime_type or "sheet" in mime_type:
        return "document"
    return "other"


def create_image_preview(content: bytes) -> tuple[bytes, str] | None:
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


def attachment_to_item(
    attachment: ServiceAttachment,
    *,
    link: OrderAttachmentLink | EquipmentAttachmentLink | None = None,
    equipment_id: int | None = None,
    component_id: int | None = None,
    service_history_id: int | None = None,
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
        "service_history_id": service_history_id,
    }


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


def legacy_attachment_items(
    order: Order,
    normalized_file_ids: set[str],
    normalized_source_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
    raw_items = meta.get("telegram_attachments")
    if not isinstance(raw_items, list):
        return []
    result: list[dict[str, Any]] = []
    normalized_source_keys = normalized_source_keys or set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        file_id = str(raw.get("file_id") or "").strip()
        source_key = legacy_attachment_source_key(int(order.id or 0), raw)
        if (file_id and file_id in normalized_file_ids) or source_key in normalized_source_keys:
            continue
        mime_type = str(raw.get("mime_type") or "application/octet-stream")
        captured_at = _parse_datetime(raw.get("attached_at"))
        result.append(
            {
                "id": None,
                "legacy_key": f"telegram:{index}:{file_id or source_key[:12]}",
                "legacy": True,
                "file_kind": attachment_file_kind(mime_type),
                "category": str(raw.get("purpose") or "other"),
                "filename": str(raw.get("filename") or f"Telegram файл {index + 1}"),
                "mime_type": mime_type,
                "size_bytes": int(raw.get("size_bytes") or 0),
                "caption": None,
                "transcript": None,
                "source": "telegram_bot",
                "processing_status": "migration_required",
                "processing_error": "Файл найден в старых данных и ожидает безопасного переноса.",
                "captured_at": captured_at,
                "created_at": captured_at or order.created_at,
                "preview_available": False,
                "equipment_id": None,
                "component_id": None,
                "service_history_id": None,
            }
        )
    return result
