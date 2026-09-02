import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import OrderProposal, OutgoingEmail
from models.tenancy import TenantScope
from modules.documents.application.delivery_service import (
    ManagedDocumentDeliveryService,
)
from services.document_service import DocumentService
from services.order_proposal_lifecycle import PROPOSAL_STATUS_SENT, sync_selected_proposal_status
from services.tenant_entity_access_service import TenantEntityAccessService


@dataclass(frozen=True)
class MailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"
    metadata: Optional[Dict[str, Any]] = None


class PartnerTenantSmtpUnavailableError(RuntimeError):
    """Global MVN SMTP must never impersonate a partner tenant."""


MAX_ORDER_EMAIL_DOCUMENTS = 10
MAX_ORDER_EMAIL_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024


class MailSmtpService:
    @staticmethod
    def _configured_from_email() -> str:
        return settings.MAIL_FROM_EMAIL or settings.MAIL_SMTP_USERNAME

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        message = str(exc)
        for secret in (settings.MAIL_SMTP_PASSWORD, settings.MAIL_IMAP_PASSWORD):
            if secret:
                message = message.replace(secret, "***")
        return message or exc.__class__.__name__

    @staticmethod
    def build_message(
        *,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[MailAttachment]] = None,
    ) -> EmailMessage:
        from_email = MailSmtpService._configured_from_email()
        if not from_email:
            raise RuntimeError("SMTP from email is not configured")
        if not body_text and not body_html:
            raise ValueError("Either body_text or body_html is required")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((settings.MAIL_FROM_NAME or "", from_email))
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        for attachment in attachments or []:
            maintype, _, subtype = attachment.mime_type.partition("/")
            msg.add_attachment(
                attachment.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        return msg

    @staticmethod
    def send_message(message: EmailMessage) -> None:
        if not settings.MAIL_SMTP_USERNAME or not settings.MAIL_SMTP_PASSWORD:
            raise RuntimeError("SMTP credentials are not configured")
        if settings.MAIL_SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.MAIL_SMTP_HOST, settings.MAIL_SMTP_PORT, timeout=30) as smtp:
                smtp.login(settings.MAIL_SMTP_USERNAME, settings.MAIL_SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.MAIL_SMTP_HOST, settings.MAIL_SMTP_PORT, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(settings.MAIL_SMTP_USERNAME, settings.MAIL_SMTP_PASSWORD)
                smtp.send_message(message)

    @staticmethod
    async def send_and_record(
        session: AsyncSession,
        *,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
        order_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        attachments: Optional[List[MailAttachment]] = None,
    ) -> OutgoingEmail:
        attachment_meta: List[Dict[str, Any]] = []
        for item in attachments or []:
            attachment_meta.append(
                {
                    "filename": item.filename,
                    "mime_type": item.mime_type,
                    "size": len(item.content),
                    **dict(item.metadata or {}),
                }
            )
        row = OutgoingEmail(
            status="pending",
            order_id=order_id,
            customer_id=customer_id,
            recipient_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            from_email=MailSmtpService._configured_from_email(),
            from_name=settings.MAIL_FROM_NAME,
            reply_to=reply_to,
            attachments=attachment_meta,
        )
        session.add(row)
        await session.flush()
        try:
            message = MailSmtpService.build_message(
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                reply_to=reply_to,
                attachments=attachments,
            )
            MailSmtpService.send_message(message)
        except Exception as exc:
            row.status = "failed"
            row.error = MailSmtpService._sanitize_error(exc)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            raise RuntimeError(row.error) from exc

        row.status = "sent"
        row.sent_at = datetime.now()
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @staticmethod
    async def send_order_email(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        order_id: int,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
        document_ids: Optional[List[int]] = None,
    ) -> OutgoingEmail:
        if not tenant_scope.is_system:
            raise PartnerTenantSmtpUnavailableError(
                "Отправка через почту «Мастер Воздуха» недоступна партнерскому аккаунту"
            )
        normalized_document_ids = list(
            dict.fromkeys(int(value) for value in (document_ids or []))
        )
        if len(normalized_document_ids) > MAX_ORDER_EMAIL_DOCUMENTS:
            raise ValueError(
                f"За одно письмо можно отправить не более {MAX_ORDER_EMAIL_DOCUMENTS} документов"
            )
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            raise ValueError("Order not found")

        attachments: List[MailAttachment] = []
        has_offer_document = False
        offer_proposal_ids: set[int] = set()
        sent_document_types: set[str] = set()
        native_document_ids: list[int] = []
        total_attachment_bytes = 0
        for doc_id in normalized_document_ids:
            doc = await TenantEntityAccessService.get_order_document(
                session,
                doc_id,
                tenant_scope=tenant_scope,
            )
            if not doc or doc.order_id != order_id:
                raise ValueError(f"Document {doc_id} not found on order")
            if DocumentService._is_native_managed_document(doc):
                if doc.status not in {"issued", "sent", "signed"}:
                    raise ValueError(
                        f"Document {doc_id} must be issued before sending"
                    )
                native_document_ids.append(int(doc.id))
            sent_document_types.add(doc.doc_type)
            if doc.doc_type == "offer":
                has_offer_document = True
                if doc.proposal_id is not None:
                    offer_proposal_ids.add(doc.proposal_id)
            stream, filename = await DocumentService.get_download_stream(
                session,
                doc_id,
                tenant_scope=tenant_scope,
            )
            if not stream:
                raise ValueError(f"Document {doc_id} cannot be downloaded")
            encoded = getattr(stream, "getvalue", lambda: bytes(stream))()
            if len(encoded) > MAX_ORDER_EMAIL_ATTACHMENT_BYTES:
                raise ValueError("Один из PDF слишком велик для отправки по почте")
            total_attachment_bytes += len(encoded)
            if total_attachment_bytes > MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES:
                raise ValueError("Общий размер PDF слишком велик для одного письма")
            attachments.append(
                MailAttachment(
                    filename=filename or f"document-{doc_id}.pdf",
                    content=encoded,
                    mime_type="application/pdf",
                    metadata={
                        "document_id": int(doc_id),
                        "document_type": doc.doc_type,
                        "document_number": doc.number,
                    },
                )
            )

        email_row = await MailSmtpService.send_and_record(
            session,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            reply_to=reply_to,
            order_id=order_id,
            customer_id=order.customer_id,
            attachments=attachments,
        )
        sent_at = email_row.sent_at or datetime.now()
        if has_offer_document:
            if offer_proposal_ids:
                proposals = list(
                    (
                        await session.execute(
                            select(OrderProposal).where(
                                OrderProposal.order_id == order_id,
                                OrderProposal.id.in_(offer_proposal_ids),
                            )
                        )
                    ).scalars().all()
                )
            else:
                proposals = list(
                    (
                        await session.execute(
                            select(OrderProposal).where(
                                OrderProposal.order_id == order_id,
                                OrderProposal.is_selected.is_(True),
                                OrderProposal.is_archived.is_(False),
                            )
                        )
                    ).scalars().all()
                )
            for proposal in proposals:
                proposal.status = PROPOSAL_STATUS_SENT
                sync_selected_proposal_status(order, proposal, now=sent_at)
                session.add(proposal)
            if not proposals:
                order.proposal_status = PROPOSAL_STATUS_SENT
                order.proposal_sent_at = sent_at
                order.negotiation_status = "proposal_sent"
                order.negotiation_status_changed_at = sent_at

        order_status = getattr(order.status, "value", order.status)
        if order_status == "negotiation":
            if "invoice" in sent_document_types:
                order.negotiation_status = "awaiting_payment"
                order.negotiation_status_changed_at = sent_at
            elif "contract" in sent_document_types:
                order.negotiation_status = "awaiting_signature"
                order.negotiation_status_changed_at = sent_at

        if sent_document_types:
            session.add(order)
        if native_document_ids:
            await ManagedDocumentDeliveryService.mark_sent(
                session,
                tenant_scope=tenant_scope,
                document_ids=native_document_ids,
                sent_at=sent_at,
            )
            await session.refresh(email_row)
        elif sent_document_types:
            await session.commit()
            await session.refresh(email_row)
        return email_row
