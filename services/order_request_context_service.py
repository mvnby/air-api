"""Project existing request evidence without fetching, importing or modifying originals."""

from sqlalchemy import or_, select

from models import OrderAttachmentLink, ServiceAttachment
from models.incoming_mail import IncomingMail
from schemas_order_request_context import ManagerOrderRequestContext, OrderRequestFile, OrderRequestSourceText
from services.incoming_mail_service import IncomingMailService
from services.service_attachment_service import ServiceAttachmentService
from services.tenant_entity_access_service import TenantEntityAccessService


class OrderRequestContextService:
    @classmethod
    async def read(cls, session, *, order_id, actor):
        scope = actor.tenant_scope
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope)
        if order is None:
            return None
        data = await ServiceAttachmentService.list_order_attachments(session, order_id=order_id, tenant_scope=scope)
        stored = {row.id: row for row in (await session.execute(select(ServiceAttachment.id, ServiceAttachment.content_hash, ServiceAttachment.storage_key).join(
            OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id,
        ).where(OrderAttachmentLink.order_id == order_id, OrderAttachmentLink.archived_at.is_(None),
                ServiceAttachment.archived_at.is_(None)))).all()}
        result = ManagerOrderRequestContext()
        seen = {}
        for item in data["items"]:
            stored_file = stored.get(item["id"])
            digest = stored_file.content_hash if stored_file else None
            key = ("sha256", digest) if digest else ("service", item["id"] or item.get("legacy_key"))
            if key in seen:
                continue
            seen[key] = len(result.files)
            label = "Из письма заказчика" if item["source"].startswith("email_") else (
                "Из тендера" if item["source"] == "belzakupki" else "Файл заказа")
            result.files.append(OrderRequestFile(**item, available=bool(stored_file and stored_file.storage_key), origin_label=label))

        meta = order.technical_meta or {}
        # Mailbox evidence uses the same live access check as reading the saved message.
        # Non-system companies never query the shared system mailbox.
        if order.lead_source == "email" and scope.is_system:
            await IncomingMailService._require_access(session, actor)
            predicates = [IncomingMail.order_id == order_id]
            message_id = meta.get("email_source_message_id")
            if message_id:
                predicates.append(IncomingMail.message_id == message_id)
            messages = (await session.execute(select(IncomingMail).where(
                IncomingMail.tenant_id == scope.tenant_id, IncomingMail.account_id == "system",
                or_(*predicates),
            ).order_by(IncomingMail.received_at, IncomingMail.id))).scalars().all()
            for message in messages:
                result.sources.append(OrderRequestSourceText(
                    label=f"Исходное письмо: {message.subject or 'Без темы'}",
                    text=message.body_text, url=f"/manager/mail?emailId={-message.id}",
                ))
                for position, file in enumerate(message.attachments or []):
                    digest = file.get("sha256")
                    key = ("sha256", digest) if digest else ("mail", message.id, position)
                    file_id = file.get("id")
                    available = bool(file.get("available") and file_id)
                    existing = seen.get(key)
                    if existing is not None and (result.files[existing].available or not available):
                        continue
                    projected = OrderRequestFile(
                        id=-file_id if file_id else None, legacy_key=f"mail:{message.id}:{position}",
                        filename=file["filename"], mime_type=file.get("mime_type") or "application/octet-stream",
                        size_bytes=file.get("size") or 0, created_at=message.received_at,
                        source="incoming_mail", origin_label="Из письма заказчика", category="document",
                        available=available, processing_status="ready" if available else "unavailable",
                        processing_error=None if available else "Оригинал не сохранён в почтовом архиве.",
                        mail_message_id=-message.id, mail_attachment_id=file_id,
                    )
                    if existing is None:
                        seen[key] = len(result.files)
                        result.files.append(projected)
                    else:
                        result.files[existing] = projected
        if order.lead_source == "email" and not result.sources:
            text = str(meta.get("email_source_text") or "")
            if text:
                result.sources.append(OrderRequestSourceText(label="Сохранённый текст исходного письма", text=text,
                    truncated=bool(meta.get("email_source_text_truncated"))))
            else:
                result.warnings.append("Исходный текст письма не сохранён. Рабочее описание могло быть изменено менеджером.")
        if order.lead_source == "belzakupki":
            from services.belzakupki_source_equipment_service import BelzakupkiSourceEquipmentService
            try:
                card = await BelzakupkiSourceEquipmentService.card(session, order_id=order_id, scope=scope)
            except ValueError:
                result.warnings.append("Ссылка и текст исходного тендера не сохранены. Проверьте файлы и рабочее описание.")
            else:
                result.sources.append(OrderRequestSourceText(label="Проработанная заявка тендера",
                    text="\n\n".join(filter(None, [card.title, card.work_summary, card.equipment_details])), url=card.source_url))
        for skipped in meta.get("email_attachments_skipped") or []:
            result.warnings.append(f"Не сохранено при импорте: {skipped.get('filename', 'Файл')}. Проверьте исходное письмо.")
        return result
