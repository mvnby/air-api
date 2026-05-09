import email
import imaplib
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from services.bank_email_parser_service import BankEmailParserService
from services.bank_receipt_service import BankReceiptImportResult, BankReceiptService


class MailImapService:
    @staticmethod
    def _decode_header_value(raw: Optional[str]) -> str:
        parts = decode_header(raw or "")
        decoded = []
        for value, charset in parts:
            if isinstance(value, bytes):
                decoded.append(value.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(value)
        return "".join(decoded).strip()

    @staticmethod
    def _extract_body(msg: Message) -> str:
        if msg.is_multipart():
            html_fallback = ""
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                disposition = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in disposition:
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if part.get_content_type() == "text/plain":
                    return text
                if part.get_content_type() == "text/html" and not html_fallback:
                    html_fallback = text
            return html_fallback

        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload() or "")
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    @staticmethod
    def _connect() -> imaplib.IMAP4:
        if not settings.MAIL_IMAP_USERNAME or not settings.MAIL_IMAP_PASSWORD:
            raise RuntimeError("IMAP credentials are not configured")
        if settings.MAIL_IMAP_USE_SSL:
            client: imaplib.IMAP4 = imaplib.IMAP4_SSL(settings.MAIL_IMAP_HOST, settings.MAIL_IMAP_PORT)
        else:
            client = imaplib.IMAP4(settings.MAIL_IMAP_HOST, settings.MAIL_IMAP_PORT)
        client.login(settings.MAIL_IMAP_USERNAME, settings.MAIL_IMAP_PASSWORD)
        return client

    @staticmethod
    async def import_bank_receipts(session: AsyncSession, *, limit: int = 50) -> BankReceiptImportResult:
        result = BankReceiptImportResult()
        client = MailImapService._connect()
        try:
            client.select(settings.MAIL_IMAP_BANK_FOLDER or "INBOX", readonly=not bool(settings.MAIL_IMAP_PROCESSED_FOLDER))
            status, payload = client.search(None, "FROM", f'"{BankEmailParserService.BANK_SENDER}"')
            if status != "OK":
                raise RuntimeError("IMAP search failed")

            message_ids = list(reversed((payload[0] or b"").split()))[: max(1, int(limit or 50))]
            for imap_id in reversed(message_ids):
                result.processed += 1
                status, message_data = client.fetch(imap_id, "(RFC822)")
                if status != "OK" or not message_data:
                    result.failed += 1
                    continue

                raw_email = next((item[1] for item in message_data if isinstance(item, tuple)), None)
                if not raw_email:
                    result.failed += 1
                    continue

                msg = email.message_from_bytes(raw_email)
                subject = MailImapService._decode_header_value(msg.get("Subject"))
                sender_email = parseaddr(MailImapService._decode_header_value(msg.get("From")))[1].lower()
                if not BankEmailParserService.is_bank_credit_email(sender_email, subject):
                    continue
                raw_body = MailImapService._extract_body(msg)
                receipt, created = await BankReceiptService.process_email(
                    session,
                    sender_email=sender_email,
                    subject=subject,
                    raw_body=raw_body,
                    message_id=msg.get("Message-ID"),
                    email_date_raw=msg.get("Date"),
                )
                if created:
                    result.created += 1
                else:
                    result.duplicates += 1
                if receipt.id is not None:
                    result.receipt_ids.append(int(receipt.id))
                if created and settings.MAIL_IMAP_PROCESSED_FOLDER:
                    client.copy(imap_id, settings.MAIL_IMAP_PROCESSED_FOLDER)
                    client.store(imap_id, "+FLAGS", "\\Deleted")

            if settings.MAIL_IMAP_PROCESSED_FOLDER:
                client.expunge()
            return result
        finally:
            try:
                client.close()
            except Exception:
                pass
            client.logout()
