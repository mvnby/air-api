"""Read-only access to original MIME files for older imported email leads."""

from __future__ import annotations

import email
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.message import Message
from email.utils import parseaddr

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models import LeadSource
from models.tenancy import TenantScope
from services.mail_imap_service import MailImapService
from services.tenant_entity_access_service import TenantEntityAccessService


MAX_EMAIL_BYTES = 30 * 1024 * 1024
MAX_EMAIL_ATTACHMENTS = 20


@dataclass(frozen=True)
class OriginalEmailFile:
    position: int
    filename: str
    content_type: str
    content: bytes


class EmailLeadOriginalAttachmentService:
    @staticmethod
    async def load(
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
    ) -> list[OriginalEmailFile] | None:
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=tenant_scope)
        if order is None or order.lead_source != LeadSource.EMAIL:
            return None
        meta = order.technical_meta or {}
        message_id = str(meta.get("email_source_message_id") or "").strip()
        sender = str(meta.get("email_sender") or "").strip().lower()
        subject = str(meta.get("email_subject") or "").strip()
        date_raw = str(meta.get("email_date") or "").strip()
        try:
            email_date = datetime.fromisoformat(date_raw).date()
        except ValueError:
            return None
        if not message_id or not sender or not subject or not re.fullmatch(r"<[A-Za-z0-9._%+@=-]{1,240}>", message_id):
            return None
        message = await EmailLeadOriginalAttachmentService._find_message(message_id, sender, subject, email_date)
        if message is None:
            return None
        originals = MailImapService._extract_original_attachments(message)
        return [
            OriginalEmailFile(index, item.filename, item.content_type, item.content)
            for index, item in enumerate(originals[:MAX_EMAIL_ATTACHMENTS])
        ]

    @staticmethod
    async def _find_message(message_id: str, sender: str, subject: str, email_date: date) -> Message | None:
        client = await MailImapService._connect_async()
        try:
            folders = dict.fromkeys(filter(None, (
                settings.MAIL_IMAP_LEAD_FOLDER or "INBOX",
                settings.MAIL_IMAP_LEAD_PROCESSED_FOLDER,
            )))
            for folder in folders:
                selected, _ = await MailImapService._imap_call(client.select, folder, readonly=True)
                if selected != "OK":
                    continue
                since = (email_date - timedelta(days=1)).strftime("%d-%b-%Y")
                before = (email_date + timedelta(days=2)).strftime("%d-%b-%Y")
                status, ids = await MailImapService._imap_call(
                    client.uid, "SEARCH", None, "SINCE", since, "BEFORE", before,
                )
                if status != "OK" or not ids:
                    continue
                for uid in reversed((ids[0] or b"").split()[-200:]):
                    status, header_data = await MailImapService._imap_call(
                        client.uid, "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT)])",
                    )
                    if status != "OK":
                        continue
                    header = next((part[1] for part in header_data or () if isinstance(part, tuple)), None)
                    if not header:
                        continue
                    header_message = email.message_from_bytes(header)
                    found_sender = parseaddr(MailImapService._decode_header_value(header_message.get("From")))[1].lower()
                    found_subject = MailImapService._decode_header_value(header_message.get("Subject"))
                    if str(header_message.get("Message-ID") or "").strip() != message_id or found_sender != sender or found_subject != subject:
                        continue
                    status, data = await MailImapService._imap_call(client.uid, "FETCH", uid, "(BODY.PEEK[])")
                    if status != "OK":
                        continue
                    raw = next((part[1] for part in data or () if isinstance(part, tuple)), None)
                    if not raw or len(raw) > MAX_EMAIL_BYTES:
                        continue
                    message = email.message_from_bytes(raw)
                    if str(message.get("Message-ID") or "").strip() == message_id:
                        return message
            return None
        finally:
            await MailImapService._close_async(client)
