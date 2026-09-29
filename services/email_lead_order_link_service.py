"""Resolve a follow-up email lead into an existing order without losing its origin."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import (
    Customer,
    LeadSource,
    Order,
    OrderAttachmentLink,
    OrderDocument,
    OrderProposal,
    OrderStatus,
    OutgoingEmail,
    ServiceAttachment,
)
from models.tenancy import TenantScope
from services.email_lead_original_attachment_service import EmailLeadOriginalAttachmentService
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_entity_access_service import TenantEntityAccessService


class EmailLeadLinkError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class EmailLeadOrderLinkService:
    @staticmethod
    async def _orders(
        session: AsyncSession,
        *,
        source_order_id: int,
        target_order_id: int,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> tuple[Order, Order]:
        if source_order_id == target_order_id:
            raise EmailLeadLinkError("Нельзя привязать письмо к тому же обращению")
        source = await TenantEntityAccessService.get_order(
            session, source_order_id, tenant_scope=tenant_scope, for_update=for_update,
        )
        target = await TenantEntityAccessService.get_order(
            session, target_order_id, tenant_scope=tenant_scope, for_update=for_update,
        )
        if source is None or target is None:
            raise EmailLeadLinkError("Обращение или заказ не найден", 404)
        if source.lead_source != LeadSource.EMAIL or source.status != OrderStatus.NEW_LEAD:
            raise EmailLeadLinkError("Привязать можно только входящее письмо без отдельной сделки")
        if target.status == OrderStatus.NEW_LEAD or target.linked_order_id is not None:
            raise EmailLeadLinkError("Выберите существующий заказ в работе или архиве")
        if source.linked_order_id is not None and source.linked_order_id != target_order_id:
            raise EmailLeadLinkError(
                f"Письмо уже связано с заказом #{source.linked_order_id}; сначала снимите эту связь", 409,
            )
        return source, target

    @staticmethod
    async def preview_target(
        session: AsyncSession,
        *,
        source_order_id: int,
        target_order_id: int,
        tenant_scope: TenantScope,
    ) -> dict[str, object]:
        _, target = await EmailLeadOrderLinkService._orders(
            session,
            source_order_id=source_order_id,
            target_order_id=target_order_id,
            tenant_scope=tenant_scope,
        )
        customer_name = await session.scalar(select(Customer.name).where(Customer.id == target.customer_id)) if target.customer_id else None
        return {
            "order_id": target_order_id,
            "title": target.title or "",
            "customer_name": customer_name or "",
            "status": target.status.value if hasattr(target.status, "value") else str(target.status),
        }

    @staticmethod
    async def _active_attachments(session: AsyncSession, source_order_id: int) -> list[tuple[OrderAttachmentLink, ServiceAttachment]]:
        return list((await session.execute(
            select(OrderAttachmentLink, ServiceAttachment)
            .join(ServiceAttachment, ServiceAttachment.id == OrderAttachmentLink.attachment_id)
            .where(
                OrderAttachmentLink.order_id == source_order_id,
                OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None),
            )
        )).all())

    @staticmethod
    async def _ensure_unworked(session: AsyncSession, source: Order) -> None:
        if float(source.total_payments or 0) > 0:
            raise EmailLeadLinkError("По обращению уже есть оплата; его нельзя скрыть привязкой")
        sent_proposals = await session.scalar(
            select(func.count(OrderProposal.id)).where(
                OrderProposal.order_id == source.id,
                OrderProposal.status == "sent",
                OrderProposal.is_archived.is_(False),
            )
        )
        sent_documents = await session.scalar(
            select(func.count(OrderDocument.id)).where(
                OrderDocument.order_id == source.id,
                OrderDocument.status.in_(("issued", "sent", "signed")),
            )
        )
        sent_emails = await session.scalar(
            select(func.count(OutgoingEmail.id)).where(
                OutgoingEmail.order_id == source.id,
                OutgoingEmail.sent_at.is_not(None),
            )
        )
        if sent_proposals or sent_documents or sent_emails:
            raise EmailLeadLinkError("По обращению уже отправлены документы или письма; нужна ручная проверка")

    @staticmethod
    async def link(
        session: AsyncSession,
        *,
        source_order_id: int,
        target_order_id: int,
        linked_by: str,
        tenant_scope: TenantScope,
    ) -> dict[str, object]:
        source, _ = await EmailLeadOrderLinkService._orders(
            session,
            source_order_id=source_order_id,
            target_order_id=target_order_id,
            tenant_scope=tenant_scope,
        )
        if source.linked_order_id == target_order_id:
            mirrored = await session.scalar(select(func.count(OrderAttachmentLink.id)).where(
                OrderAttachmentLink.order_id == target_order_id,
                OrderAttachmentLink.origin_order_id == source_order_id,
                OrderAttachmentLink.archived_at.is_(None),
            ))
            return {"source_order_id": source_order_id, "target_order_id": target_order_id, "linked_files": int(mirrored or 0)}

        # Fetch the old MIME source before taking row locks. Newer email leads
        # already have their private files and do not depend on mailbox retention.
        original_files = None
        if not await EmailLeadOrderLinkService._active_attachments(session, source_order_id):
            try:
                original_files = await EmailLeadOriginalAttachmentService.load(
                    session, order_id=source_order_id, tenant_scope=tenant_scope,
                )
            except Exception as exc:
                raise EmailLeadLinkError("Оригинал письма сейчас недоступен; связь не создана", 503) from exc
            if original_files is None:
                raise EmailLeadLinkError("Оригинал письма не найден; связь не создана", 503)

        source, _ = await EmailLeadOrderLinkService._orders(
            session,
            source_order_id=source_order_id,
            target_order_id=target_order_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if source.linked_order_id == target_order_id:
            return {"source_order_id": source_order_id, "target_order_id": target_order_id, "linked_files": 0}
        await EmailLeadOrderLinkService._ensure_unworked(session, source)

        source_links = await EmailLeadOrderLinkService._active_attachments(session, source_order_id)
        if not source_links and original_files:
            meta = source.technical_meta or {}
            for item in original_files:
                suffix = Path(item.filename).suffix.lower()
                mime_type = item.content_type.lower().split(";", 1)[0]
                if mime_type not in ServiceAttachmentService.SAFE_MIME_TYPES:
                    mime_type = {
                        ".doc": "application/msword",
                        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ".pdf": "application/pdf",
                    }.get(suffix, mime_type)
                if mime_type not in ServiceAttachmentService.SAFE_MIME_TYPES:
                    continue
                if not item.content or len(item.content) > int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES):
                    continue
                await ServiceAttachmentService.create_and_link_order_attachment(
                    session,
                    order_id=source_order_id,
                    content=item.content,
                    filename=item.filename,
                    mime_type=mime_type,
                    category="document",
                    caption=f"Вложение из письма: {item.filename}",
                    source="email_lead_intake",
                    created_by=meta.get("email_sender"),
                    source_meta={
                        "intake": "email_lead",
                        "source_order_id": source_order_id,
                        "email_source_message_id": meta.get("email_source_message_id"),
                        "attachment_position": item.position,
                    },
                    tenant_scope=tenant_scope,
                    commit=False,
                )
            source_links = await EmailLeadOrderLinkService._active_attachments(session, source_order_id)
        linked_files = 0
        for source_link, attachment in source_links:
            existing = await session.scalar(select(OrderAttachmentLink).where(
                OrderAttachmentLink.order_id == target_order_id,
                OrderAttachmentLink.attachment_id == attachment.id,
            ))
            if existing is not None:
                if existing.origin_order_id == source_order_id and existing.archived_at is not None:
                    existing.archived_at = None
                    session.add(existing)
                    linked_files += 1
                continue
            session.add(OrderAttachmentLink(
                order_id=target_order_id,
                attachment_id=int(attachment.id or 0),
                origin_order_id=source_order_id,
                category=source_link.category,
                caption=f"Письмо #{source_order_id}: {attachment.original_filename}",
            ))
            linked_files += 1

        source.linked_order_id = target_order_id
        source.linked_at = datetime.now()
        source.linked_by = linked_by[:120]
        session.add(source)
        await session.commit()
        return {"source_order_id": source_order_id, "target_order_id": target_order_id, "linked_files": linked_files}

    @staticmethod
    async def unlink(
        session: AsyncSession,
        *,
        source_order_id: int,
        tenant_scope: TenantScope,
    ) -> int:
        source = await TenantEntityAccessService.get_order(
            session, source_order_id, tenant_scope=tenant_scope, for_update=True,
        )
        if source is None or source.linked_order_id is None:
            raise EmailLeadLinkError("Связь не найдена", 404)
        target_order_id = source.linked_order_id
        links = (await session.execute(select(OrderAttachmentLink).where(
            OrderAttachmentLink.order_id == target_order_id,
            OrderAttachmentLink.origin_order_id == source_order_id,
            OrderAttachmentLink.archived_at.is_(None),
        ))).scalars().all()
        now = datetime.now()
        for link in links:
            link.archived_at = now
            session.add(link)
        source.linked_order_id = None
        source.linked_at = None
        source.linked_by = None
        session.add(source)
        await session.commit()
        return target_order_id
