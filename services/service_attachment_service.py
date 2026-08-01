"""Business logic for private order and equipment attachments."""

from __future__ import annotations

import asyncio
import hmac
import mimetypes
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.config import settings
from models import (
    Customer,
    CustomerEquipment,
    EquipmentAttachmentLink,
    Order,
    OrderAttachmentLink,
    ServiceAttachment,
)
from models.tenancy import TenantScope
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    extension_for,
    get_private_attachment_storage,
    sha256_bytes,
)
from services.service_attachment_presenter import (
    attachment_file_kind,
    attachment_to_item,
    create_image_preview,
    legacy_attachment_items,
)
from services.service_attachment_link_service import ServiceAttachmentLinkService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_scope_clause


class ServiceAttachmentService:
    CATEGORIES = {
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
    def _clean_text(value: Any, *, limit: int | None = None) -> str | None:
        cleaned = " ".join(str(value or "").split()).strip()
        if not cleaned:
            return None
        return cleaned[:limit] if limit else cleaned

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
        service_history_id: int | None = None,
        transcript: str | None = None,
        captured_at: datetime | None = None,
        telegram_meta: dict[str, Any] | None = None,
        source_meta: dict[str, Any] | None = None,
        storage: PrivateAttachmentStorage | None = None,
        commit: bool = True,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Attachment is empty")
        if len(content) > int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES):
            raise ValueError("Attachment exceeds the configured size limit")
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            raise ValueError("Order not found")
        context = await ServiceAttachmentLinkService.validate_order_context(
            session,
            order=order,
            work_stage_id=work_stage_id,
            equipment_id=equipment_id,
            component_id=component_id,
            service_history_id=service_history_id,
        )
        equipment = context.equipment
        equipment_id = int(equipment.id or 0) if equipment is not None else None
        component_id = context.component_id
        service_history_id = context.service_history_id

        clean_filename = cls._clean_text(filename, limit=255) or "attachment"
        normalized_mime = cls._normalize_mime_type(mime_type, clean_filename)
        normalized_category = cls.normalize_category(category)
        digest = sha256_bytes(content)
        selected_storage = storage or get_private_attachment_storage()
        telegram_meta = telegram_meta or {}
        telegram_file_id = cls._clean_text(telegram_meta.get("file_id"), limit=255)
        telegram_chat_id = telegram_meta.get("chat_id")
        telegram_message_id = telegram_meta.get("message_id")

        if telegram_file_id:
            occurrence_filters = [
                OrderAttachmentLink.order_id == order_id,
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            ]
            if telegram_chat_id is not None and telegram_message_id is not None:
                occurrence_filters.extend(
                    [
                        ServiceAttachment.telegram_chat_id == telegram_chat_id,
                        ServiceAttachment.telegram_message_id == telegram_message_id,
                    ]
                )
            else:
                occurrence_filters.append(ServiceAttachment.telegram_file_id == telegram_file_id)
            existing_occurrence_result = await session.execute(
                select(ServiceAttachment, OrderAttachmentLink)
                .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
                .where(*occurrence_filters)
                .limit(1)
            )
            existing_occurrence = existing_occurrence_result.first()
            if existing_occurrence:
                attachment, link = existing_occurrence
                equipment_link = None
                if equipment is not None:
                    equipment_link = await session.scalar(
                        select(EquipmentAttachmentLink).where(
                            EquipmentAttachmentLink.order_attachment_link_id == int(link.id or 0),
                            EquipmentAttachmentLink.equipment_id == int(equipment.id or 0),
                        )
                    )
                    if equipment_link is None:
                        equipment_link = EquipmentAttachmentLink(
                            equipment_id=int(equipment.id or 0),
                            attachment_id=int(attachment.id or 0),
                            order_attachment_link_id=int(link.id or 0),
                        )
                    equipment_link.archived_at = None
                    equipment_link.component_id = component_id
                    equipment_link.service_history_id = service_history_id
                    equipment_link.category = normalized_category
                    equipment_link.caption = cls._clean_text(caption)
                    session.add(equipment_link)
                if commit:
                    await session.commit()
                else:
                    await session.flush()
                return attachment_to_item(
                    attachment,
                    link=link,
                    equipment_id=int(equipment.id or 0) if equipment else None,
                    component_id=equipment_link.component_id if equipment_link else None,
                    service_history_id=equipment_link.service_history_id if equipment_link else None,
                )

        reusable_binary = None
        binary_result = await session.execute(
            select(ServiceAttachment)
            .where(
                ServiceAttachment.content_hash == digest,
                ServiceAttachment.storage_provider == selected_storage.provider_name,
                ServiceAttachment.storage_key.is_not(None),
            )
            .order_by(ServiceAttachment.id.asc())
        )
        for candidate in binary_result.scalars().all():
            if candidate.storage_key and await selected_storage.exists(candidate.storage_key):
                reusable_binary = candidate
                break

        preview_key = reusable_binary.preview_storage_key if reusable_binary else None
        preview_mime = reusable_binary.preview_mime_type if reusable_binary else None
        if preview_key and not await selected_storage.exists(preview_key):
            preview_key = None
            preview_mime = None
        if reusable_binary is None:
            original = await selected_storage.save(
                content=content,
                content_hash=digest,
                extension=extension_for(clean_filename, normalized_mime),
                content_type=normalized_mime,
                variant="original",
            )
            storage_provider = original.provider
            storage_key = original.storage_key
        else:
            storage_provider = reusable_binary.storage_provider
            storage_key = reusable_binary.storage_key

        if normalized_mime.startswith("image/") and not preview_key:
            preview = await asyncio.to_thread(create_image_preview, content)
            if preview:
                preview_content, preview_mime = preview
                stored_preview = await selected_storage.save(
                    content=preview_content,
                    content_hash=sha256_bytes(preview_content),
                    extension="webp",
                    content_type=preview_mime,
                    variant="preview",
                )
                preview_key = stored_preview.storage_key

        attachment = ServiceAttachment(
            file_kind=attachment_file_kind(normalized_mime),
            original_filename=clean_filename,
            mime_type=normalized_mime,
            size_bytes=len(content),
            content_hash=digest,
            storage_provider=storage_provider,
            storage_key=storage_key,
            preview_storage_key=preview_key,
            preview_mime_type=preview_mime,
            source=source,
            processing_status="ready",
            transcript=cls._clean_text(transcript),
            source_meta={
                **dict(telegram_meta.get("source_meta") or {}),
                **dict(source_meta or {}),
            },
            telegram_file_id=telegram_file_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_user_id=telegram_meta.get("user_id"),
            captured_at=captured_at,
            created_by=created_by,
        )
        session.add(attachment)
        await session.flush()

        link = OrderAttachmentLink(
            order_id=order_id,
            attachment_id=int(attachment.id or 0),
            work_stage_id=work_stage_id,
            category=normalized_category,
            caption=cls._clean_text(caption),
        )
        session.add(link)
        await session.flush()

        if equipment is not None:
            equipment_link = EquipmentAttachmentLink(
                equipment_id=int(equipment.id or 0),
                attachment_id=int(attachment.id or 0),
                order_attachment_link_id=int(link.id or 0),
                component_id=component_id,
                service_history_id=service_history_id,
                category=normalized_category,
                caption=cls._clean_text(caption),
            )
            session.add(equipment_link)

        if commit:
            await session.commit()
            await session.refresh(attachment)
        else:
            await session.flush()
        return attachment_to_item(
            attachment,
            link=link,
            equipment_id=equipment_id,
            component_id=component_id,
            service_history_id=service_history_id,
        )

    @staticmethod
    async def order_attachment_counts(
        session: AsyncSession,
        *,
        order_ids: list[int],
        tenant_scope: TenantScope,
    ) -> dict[int, int]:
        normalized_ids = sorted(
            {int(order_id) for order_id in order_ids if int(order_id) > 0}
        )
        if not normalized_ids:
            return {}
        rows = (
            await session.execute(
                select(OrderAttachmentLink.order_id, func.count(OrderAttachmentLink.id))
                .join(Order, Order.id == OrderAttachmentLink.order_id)
                .outerjoin(Customer, Customer.id == Order.customer_id)
                .join(
                    ServiceAttachment,
                    ServiceAttachment.id == OrderAttachmentLink.attachment_id,
                )
                .where(
                    OrderAttachmentLink.order_id.in_(normalized_ids),
                    OrderAttachmentLink.archived_at.is_(None),
                    ServiceAttachment.archived_at.is_(None),
                    TenantEntityAccessService.order_clause(tenant_scope),
                    TenantEntityAccessService.order_customer_clause(tenant_scope),
                )
                .group_by(OrderAttachmentLink.order_id)
            )
        ).all()
        return {int(order_id): int(count) for order_id, count in rows}

    @classmethod
    async def list_order_attachments(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            return None
        result = await session.execute(
            select(ServiceAttachment, OrderAttachmentLink, EquipmentAttachmentLink)
            .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
            .outerjoin(
                EquipmentAttachmentLink,
                (EquipmentAttachmentLink.order_attachment_link_id == OrderAttachmentLink.id)
                & (EquipmentAttachmentLink.archived_at.is_(None)),
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
                attachment_to_item(
                    attachment,
                    link=link,
                    equipment_id=equipment_link.equipment_id if equipment_link else None,
                    component_id=equipment_link.component_id if equipment_link else None,
                    service_history_id=equipment_link.service_history_id if equipment_link else None,
                )
            )
        normalized_file_ids = {
            str(attachment.telegram_file_id)
            for attachment, _, _ in rows
            if attachment.telegram_file_id
        }
        normalized_source_keys = {
            str((attachment.source_meta or {}).get("legacy_source_key"))
            for attachment, _, _ in rows
            if isinstance(attachment.source_meta, dict)
            and (attachment.source_meta or {}).get("legacy_source_key")
        }
        items.extend(
            legacy_attachment_items(
                order,
                normalized_file_ids,
                normalized_source_keys,
            )
        )
        return {"items": items, "total": len(items)}

    @classmethod
    async def list_equipment_attachments(
        cls,
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        equipment = await TenantEntityAccessService.get_equipment(
            session,
            equipment_id,
            tenant_scope=tenant_scope,
        )
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
            attachment_to_item(
                attachment,
                link=equipment_link,
                equipment_id=equipment_id,
                component_id=equipment_link.component_id,
                service_history_id=equipment_link.service_history_id,
            )
            for attachment, equipment_link in result.all()
        ]
        return {"items": items, "total": len(items)}

    @classmethod
    async def order_attachment_count(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        tenant_scope: TenantScope,
    ) -> int:
        owned_order = await TenantEntityAccessService.get_order(
            session,
            int(order.id or 0),
            tenant_scope=tenant_scope,
        )
        if owned_order is None:
            return 0
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
            select(ServiceAttachment.telegram_file_id, ServiceAttachment.source_meta)
            .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
            .where(
                OrderAttachmentLink.order_id == int(order.id or 0),
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            )
        )
        normalized_rows = normalized_result.all()
        normalized_ids = {str(file_id) for file_id, _ in normalized_rows if file_id}
        normalized_source_keys = {
            str(source_meta.get("legacy_source_key"))
            for _, source_meta in normalized_rows
            if isinstance(source_meta, dict) and source_meta.get("legacy_source_key")
        }
        return int(db_count or 0) + len(
            legacy_attachment_items(order, normalized_ids, normalized_source_keys)
        )

    @classmethod
    async def update_attachment(
        cls,
        session: AsyncSession,
        *,
        attachment_id: int,
        order_id: int | None,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return None
        if "transcript" in payload and not await cls._all_active_links_belong_to_scope(
            session,
            attachment_id=attachment_id,
            tenant_scope=tenant_scope,
        ):
            return None
        link = None
        if order_id is not None:
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            if order is None:
                return None
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
        elif not await cls._all_active_links_belong_to_scope(
            session,
            attachment_id=attachment_id,
            tenant_scope=tenant_scope,
        ):
            return None
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
        service_history_id_for_response: int | None = None
        if {"equipment_id", "component_id", "service_history_id"}.intersection(payload):
            if order_id is None:
                raise ValueError("order_id is required to change equipment link")
            if link is None:
                raise ValueError("Order or attachment link not found")
            await ServiceAttachmentLinkService.replace_equipment_link(
                session,
                order=order,
                order_link=link,
                attachment_id=attachment_id,
                payload=payload,
            )

        active_equipment_link = None
        if link is not None:
            active_equipment_link_result = await session.execute(
                select(EquipmentAttachmentLink).where(
                    EquipmentAttachmentLink.order_attachment_link_id == int(link.id or 0),
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
            service_history_id_for_response = active_equipment_link.service_history_id
        attachment.updated_at = datetime.now()
        session.add(attachment)
        if link:
            session.add(link)
        await session.commit()
        await session.refresh(attachment)
        return attachment_to_item(
            attachment,
            link=link,
            equipment_id=equipment_id_for_response,
            component_id=component_id_for_response,
            service_history_id=service_history_id_for_response,
        )

    @staticmethod
    async def _has_active_link(session: AsyncSession, *, attachment_id: int) -> bool:
        active_order_link = await session.scalar(
            select(OrderAttachmentLink.id).where(
                OrderAttachmentLink.attachment_id == attachment_id,
                OrderAttachmentLink.archived_at.is_(None),
            ).limit(1)
        )
        if active_order_link is not None:
            return True
        active_equipment_link = await session.scalar(
            select(EquipmentAttachmentLink.id).where(
                EquipmentAttachmentLink.attachment_id == attachment_id,
                EquipmentAttachmentLink.archived_at.is_(None),
            ).limit(1)
        )
        return active_equipment_link is not None

    @staticmethod
    async def _has_active_link_for_scope(
        session: AsyncSession,
        *,
        attachment_id: int,
        tenant_scope: TenantScope,
    ) -> bool:
        active_order_link = await session.scalar(
            select(OrderAttachmentLink.id)
            .join(Order, Order.id == OrderAttachmentLink.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                OrderAttachmentLink.attachment_id == attachment_id,
                OrderAttachmentLink.archived_at.is_(None),
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            )
            .limit(1)
        )
        if active_order_link is not None:
            return True
        active_equipment_link = await session.scalar(
            select(EquipmentAttachmentLink.id)
            .join(
                CustomerEquipment,
                CustomerEquipment.id == EquipmentAttachmentLink.equipment_id,
            )
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .where(
                EquipmentAttachmentLink.attachment_id == attachment_id,
                EquipmentAttachmentLink.archived_at.is_(None),
                tenant_scope_clause(Customer, tenant_scope),
            )
            .limit(1)
        )
        return active_equipment_link is not None

    @staticmethod
    async def _all_active_links_belong_to_scope(
        session: AsyncSession,
        *,
        attachment_id: int,
        tenant_scope: TenantScope,
    ) -> bool:
        all_order_link_ids = set(
            (
                await session.execute(
                    select(OrderAttachmentLink.id).where(
                        OrderAttachmentLink.attachment_id == attachment_id,
                        OrderAttachmentLink.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        scoped_order_link_ids = set(
            (
                await session.execute(
                    select(OrderAttachmentLink.id)
                    .join(Order, Order.id == OrderAttachmentLink.order_id)
                    .outerjoin(Customer, Customer.id == Order.customer_id)
                    .where(
                        OrderAttachmentLink.attachment_id == attachment_id,
                        OrderAttachmentLink.archived_at.is_(None),
                        TenantEntityAccessService.order_clause(tenant_scope),
                        TenantEntityAccessService.order_customer_clause(
                            tenant_scope
                        ),
                    )
                )
            ).scalars().all()
        )
        all_equipment_link_ids = set(
            (
                await session.execute(
                    select(EquipmentAttachmentLink.id).where(
                        EquipmentAttachmentLink.attachment_id == attachment_id,
                        EquipmentAttachmentLink.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        scoped_equipment_link_ids = set(
            (
                await session.execute(
                    select(EquipmentAttachmentLink.id)
                    .join(
                        CustomerEquipment,
                        CustomerEquipment.id == EquipmentAttachmentLink.equipment_id,
                    )
                    .join(Customer, Customer.id == CustomerEquipment.customer_id)
                    .where(
                        EquipmentAttachmentLink.attachment_id == attachment_id,
                        EquipmentAttachmentLink.archived_at.is_(None),
                        tenant_scope_clause(
                            Customer,
                            tenant_scope,
                        ),
                    )
                )
            ).scalars().all()
        )
        return bool(all_order_link_ids or all_equipment_link_ids) and (
            all_order_link_ids == scoped_order_link_ids
            and all_equipment_link_ids == scoped_equipment_link_ids
        )

    @staticmethod
    async def archive_attachment(
        session: AsyncSession,
        *,
        attachment_id: int,
        order_id: int | None = None,
        tenant_scope: TenantScope,
    ) -> bool:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return False
        if order_id is not None:
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            if order is None:
                return False
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
            equipment_links_result = await session.execute(
                select(EquipmentAttachmentLink).where(
                    EquipmentAttachmentLink.order_attachment_link_id == int(link.id or 0),
                    EquipmentAttachmentLink.archived_at.is_(None),
                )
            )
            for equipment_link in equipment_links_result.scalars().all():
                equipment_link.archived_at = datetime.now()
                session.add(equipment_link)
        else:
            if not await ServiceAttachmentService._all_active_links_belong_to_scope(
                session,
                attachment_id=attachment_id,
                tenant_scope=tenant_scope,
            ):
                return False
            order_links_result = await session.execute(
                select(OrderAttachmentLink).where(
                    OrderAttachmentLink.attachment_id == attachment_id,
                    OrderAttachmentLink.archived_at.is_(None),
                )
            )
            for order_link in order_links_result.scalars().all():
                order_link.archived_at = datetime.now()
                session.add(order_link)
            equipment_links_result = await session.execute(
                select(EquipmentAttachmentLink).where(
                    EquipmentAttachmentLink.attachment_id == attachment_id,
                    EquipmentAttachmentLink.archived_at.is_(None),
                )
            )
            for equipment_link in equipment_links_result.scalars().all():
                equipment_link.archived_at = datetime.now()
                session.add(equipment_link)

        await session.flush()
        if not await ServiceAttachmentService._has_active_link(session, attachment_id=attachment_id):
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
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        attachment = await session.get(ServiceAttachment, attachment_id)
        if not attachment or attachment.archived_at is not None:
            return None
        if not await cls._has_active_link_for_scope(
            session,
            attachment_id=attachment_id,
            tenant_scope=tenant_scope,
        ):
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
        if not await ServiceAttachmentService._has_active_link(session, attachment_id=attachment_id):
            raise FileNotFoundError("Attachment not found")
        normalized_variant = "preview" if variant == "preview" and attachment.preview_storage_key else "original"
        key = attachment.preview_storage_key if normalized_variant == "preview" else attachment.storage_key
        if not key:
            raise FileNotFoundError("Attachment source is not available")
        selected_storage = storage or get_private_attachment_storage(attachment.storage_provider)
        content = await selected_storage.read(key)
        mime_type = attachment.preview_mime_type if normalized_variant == "preview" else attachment.mime_type
        return attachment, content, mime_type or "application/octet-stream"
