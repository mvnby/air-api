import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models import Order, OrderDocument, OutgoingEmail
from services.document_service import DocumentService


@dataclass(frozen=True)
class MailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


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
        attachment_meta: List[Dict[str, Any]] = [
            {"filename": item.filename, "mime_type": item.mime_type, "size": len(item.content)}
            for item in attachments or []
        ]
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
        order_id: int,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
        document_ids: Optional[List[int]] = None,
    ) -> OutgoingEmail:
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        attachments: List[MailAttachment] = []
        for doc_id in document_ids or []:
            doc = await session.get(OrderDocument, doc_id)
            if not doc or doc.order_id != order_id:
                raise ValueError(f"Document {doc_id} not found on order")
            stream, filename = await DocumentService.get_download_stream(session, doc_id)
            if not stream:
                raise ValueError(f"Document {doc_id} cannot be downloaded")
            encoded = getattr(stream, "getvalue", lambda: bytes(stream))()
            attachments.append(MailAttachment(filename=filename or f"document-{doc_id}.pdf", content=encoded, mime_type="application/pdf"))

        return await MailSmtpService.send_and_record(
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
