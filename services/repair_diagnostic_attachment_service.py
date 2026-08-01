"""Tenant/order-scoped private attachment access for repair automation."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderAttachmentLink, ServiceAttachment
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    get_private_attachment_storage,
    sha256_bytes,
)
from services.tenant_scope_service import TenantScope, storefront_scope_clause


@dataclass(frozen=True)
class PrivateOrderAttachmentSource:
    attachment_id: int
    order_id: int
    storage_provider: str
    storage_key: str
    filename: str
    mime_type: str
    content_hash: str | None
    size_bytes: int


class RepairDiagnosticAttachmentService:
    @staticmethod
    async def resolve_source(
        session: AsyncSession,
        *,
        order_id: int,
        attachment_id: int,
        tenant_scope: TenantScope,
    ) -> PrivateOrderAttachmentSource | None:
        attachment = await session.scalar(
            select(ServiceAttachment)
            .join(
                OrderAttachmentLink,
                OrderAttachmentLink.attachment_id == ServiceAttachment.id,
            )
            .join(Order, Order.id == OrderAttachmentLink.order_id)
            .where(
                ServiceAttachment.id == attachment_id,
                ServiceAttachment.archived_at.is_(None),
                ServiceAttachment.storage_key.is_not(None),
                ServiceAttachment.source == "website_repair_diagnostic",
                OrderAttachmentLink.order_id == order_id,
                OrderAttachmentLink.archived_at.is_(None),
                OrderAttachmentLink.category == "nameplate",
                storefront_scope_clause(Order, tenant_scope),
            )
            .limit(1)
        )
        source_meta = attachment.source_meta if attachment is not None else None
        if (
            attachment is None
            or not attachment.storage_key
            or not isinstance(source_meta, dict)
            or source_meta.get("intake") != "repair_diagnostic"
            or source_meta.get("photo_category") != "nameplate"
            or source_meta.get("purpose") != "repair_diagnostic_nameplate"
        ):
            return None
        return PrivateOrderAttachmentSource(
            attachment_id=int(attachment.id or 0),
            order_id=order_id,
            storage_provider=attachment.storage_provider,
            storage_key=attachment.storage_key,
            filename=attachment.original_filename,
            mime_type=attachment.mime_type,
            content_hash=attachment.content_hash,
            size_bytes=int(attachment.size_bytes or 0),
        )

    @staticmethod
    async def read_source(
        source: PrivateOrderAttachmentSource,
        *,
        storage: PrivateAttachmentStorage | None = None,
    ) -> bytes:
        selected_storage = storage or get_private_attachment_storage(
            source.storage_provider
        )
        content = await selected_storage.read(source.storage_key)
        if source.content_hash and not hmac.compare_digest(
            sha256_bytes(content),
            source.content_hash,
        ):
            raise OSError("Private attachment content hash mismatch")
        return content
