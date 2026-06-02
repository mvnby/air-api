import email
import imaplib
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from io import BytesIO
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import GlobalConfig
from services.bank_email_parser_service import BankEmailParserService
from services.bank_receipt_service import BankReceiptImportResult, BankReceiptService
from services.email_lead_intake_service import EmailLeadDecision, EmailLeadImportResult, EmailLeadIntakeService


@dataclass(frozen=True)
class AttachmentTextExtraction:
    text: str = ""
    diagnostic: Optional[str] = None


class MailImapService:
    EMAIL_LEAD_LAST_IMPORT_KEY = "mail_lead_last_import_at"
    LEGACY_DOC_MAX_BYTES = 5 * 1024 * 1024
    LEGACY_DOC_TIMEOUT_SECONDS = 8

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
    def _decode_filename(raw: Optional[str]) -> str:
        return MailImapService._decode_header_value(raw).strip()

    @staticmethod
    def _strip_html(raw: str) -> str:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", str(raw or ""), flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_pdf_text(content: bytes) -> str:
        text = ""
        try:
            from pypdf import PdfReader
        except Exception:
            PdfReader = None
        if PdfReader is not None:
            try:
                reader = PdfReader(BytesIO(content))
                chunks = [(page.extract_text() or "") for page in reader.pages[:8]]
                text = "\n".join(chunk for chunk in chunks if chunk).strip()
            except Exception:
                text = ""
        if text:
            return text

        try:
            from pdf2image import convert_from_bytes
            import pytesseract
        except Exception:
            return ""
        try:
            images = convert_from_bytes(content, first_page=1, last_page=4, dpi=200)
        except Exception:
            return ""

        chunks = []
        for image in images:
            try:
                chunks.append(pytesseract.image_to_string(image, lang="rus+eng", timeout=20))
            except Exception:
                try:
                    chunks.append(pytesseract.image_to_string(image, timeout=20))
                except Exception:
                    continue
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    @staticmethod
    def _extract_docx_text(content: bytes) -> str:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
        except Exception:
            return ""
        xml = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", " ", xml)
        return re.sub(r"[ \t]+", " ", text).strip()

    @staticmethod
    def _decode_extracted_bytes(content: bytes) -> str:
        for encoding in ("utf-8", "cp1251", "cp866"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_legacy_doc_text(content: bytes, *, max_chars: int = 4000) -> AttachmentTextExtraction:
        if len(content) > MailImapService.LEGACY_DOC_MAX_BYTES:
            size_mb = MailImapService.LEGACY_DOC_MAX_BYTES // (1024 * 1024)
            return AttachmentTextExtraction(diagnostic=f"legacy .doc не распознан: размер вложения больше {size_mb} МБ")

        antiword_path = shutil.which("antiword")
        if not antiword_path:
            return AttachmentTextExtraction(diagnostic="legacy .doc не распознан: antiword не установлен в runtime")

        try:
            with tempfile.NamedTemporaryFile(suffix=".doc") as tmp:
                tmp.write(content)
                tmp.flush()
                completed = subprocess.run(
                    [antiword_path, tmp.name],
                    capture_output=True,
                    timeout=MailImapService.LEGACY_DOC_TIMEOUT_SECONDS,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            return AttachmentTextExtraction(diagnostic="legacy .doc не распознан: истекло время обработки antiword")
        except OSError as exc:
            detail = str(exc).strip()
            return AttachmentTextExtraction(diagnostic=f"legacy .doc не распознан: ошибка запуска antiword ({detail})")

        if completed.returncode != 0:
            detail = MailImapService._decode_extracted_bytes(completed.stderr or b"").strip()
            suffix = f": {detail[:180]}" if detail else ""
            return AttachmentTextExtraction(diagnostic=f"legacy .doc не распознан: antiword вернул код {completed.returncode}{suffix}")

        text = MailImapService._decode_extracted_bytes(completed.stdout or b"")
        text = re.sub(r"\s+", " ", text).strip()[:max_chars].strip()
        if not text:
            return AttachmentTextExtraction(diagnostic="legacy .doc не распознан: antiword не извлек текст")
        return AttachmentTextExtraction(text=text)

    @staticmethod
    def _extract_attachment_text_result(
        filename: str,
        content_type: str,
        content: bytes,
        *,
        max_chars: int = 4000,
    ) -> AttachmentTextExtraction:
        lower_name = filename.lower()
        content_type = str(content_type or "").lower()
        text = ""
        if content_type.startswith("text/") or lower_name.endswith((".txt", ".csv")):
            text = content.decode("utf-8", errors="replace")
        elif content_type == "text/html" or lower_name.endswith((".html", ".htm")):
            text = MailImapService._strip_html(content.decode("utf-8", errors="replace"))
        elif content_type == "application/pdf" or lower_name.endswith(".pdf"):
            text = MailImapService._extract_pdf_text(content)
        elif (
            content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or lower_name.endswith(".docx")
        ):
            text = MailImapService._extract_docx_text(content)
        elif content_type in {"application/msword", "application/vnd.ms-word"} or lower_name.endswith(".doc"):
            return MailImapService._extract_legacy_doc_text(content, max_chars=max_chars)
        elif lower_name.endswith(".rtf"):
            text = content.decode("utf-8", errors="replace")
            text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
            text = re.sub(r"[{}\\][a-zA-Z0-9*'-]+ ?", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return AttachmentTextExtraction(text=text[:max_chars].strip())

    @staticmethod
    def _extract_attachment_text(filename: str, content_type: str, content: bytes, *, max_chars: int = 4000) -> str:
        return MailImapService._extract_attachment_text_result(
            filename=filename,
            content_type=content_type,
            content=content,
            max_chars=max_chars,
        ).text

    @staticmethod
    def _extract_attachment_texts(msg: Message) -> list[str]:
        texts: list[str] = []
        for part in msg.walk() if msg.is_multipart() else []:
            if part.get_content_maintype() == "multipart":
                continue
            filename = MailImapService._decode_filename(part.get_filename())
            disposition = str(part.get("Content-Disposition") or "").lower()
            if not filename and "attachment" not in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            extraction = MailImapService._extract_attachment_text_result(
                filename=filename or "attachment",
                content_type=part.get_content_type(),
                content=payload,
            )
            if extraction.text:
                texts.append(f"Вложение {filename or 'attachment'}:\n{extraction.text}")
            elif extraction.diagnostic:
                texts.append(f"Вложение {filename or 'attachment'}: {extraction.diagnostic}")
            elif filename:
                texts.append(f"Вложение {filename}: текст не извлечен")
        return texts

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
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value

    @staticmethod
    def _parse_email_date(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        return MailImapService._normalize_datetime(parsed)

    @staticmethod
    def _parse_iso_datetime(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return MailImapService._normalize_datetime(parsed)

    @staticmethod
    def _imap_since_date(value: datetime) -> str:
        return value.strftime("%d-%b-%Y")

    @staticmethod
    async def _get_global_config_value(session: AsyncSession, key: str) -> Optional[str]:
        result = await session.execute(select(GlobalConfig).where(GlobalConfig.key == key))
        cfg = result.scalar_one_or_none()
        return cfg.value if cfg and cfg.value is not None else None

    @staticmethod
    async def _set_global_config_value(session: AsyncSession, key: str, value: str, description: str) -> None:
        result = await session.execute(select(GlobalConfig).where(GlobalConfig.key == key))
        cfg = result.scalar_one_or_none()
        if cfg is None:
            cfg = GlobalConfig(key=key, value=value, description=description)
        else:
            cfg.value = value
            cfg.description = description
            cfg.updated_at = datetime.now()
        session.add(cfg)
        await session.commit()

    @staticmethod
    async def _email_lead_scan_since(session: AsyncSession) -> datetime:
        stored = await MailImapService._get_global_config_value(session, MailImapService.EMAIL_LEAD_LAST_IMPORT_KEY)
        parsed = MailImapService._parse_iso_datetime(stored)
        if parsed:
            return parsed
        days = max(1, int(settings.MAIL_IMAP_LEAD_INITIAL_LOOKBACK_DAYS or 5))
        return datetime.now() - timedelta(days=days)

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
                    if created:
                        result.created_receipt_ids.append(int(receipt.id))
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

    @staticmethod
    async def import_email_leads(
        session: AsyncSession,
        *,
        dry_run: bool = False,
        lookback_days: Optional[int] = None,
    ) -> EmailLeadImportResult:
        result = EmailLeadImportResult()
        scan_started_at = datetime.now()
        if lookback_days is not None:
            scan_since = scan_started_at - timedelta(days=max(1, min(30, int(lookback_days))))
        else:
            scan_since = await MailImapService._email_lead_scan_since(session)
        result.scanned_since = scan_since.isoformat(timespec="seconds")
        client = MailImapService._connect()
        try:
            processed_folder = settings.MAIL_IMAP_LEAD_PROCESSED_FOLDER or ""
            client.select(settings.MAIL_IMAP_LEAD_FOLDER or "INBOX", readonly=not bool(processed_folder))
            status, payload = client.search(None, "SINCE", MailImapService._imap_since_date(scan_since))
            if status != "OK":
                raise RuntimeError("IMAP search failed")

            message_ids = list(reversed((payload[0] or b"").split()))
            for imap_id in reversed(message_ids):
                status, message_data = client.fetch(imap_id, "(RFC822)")
                if status != "OK" or not message_data:
                    result.failed += 1
                    continue

                raw_email = next((item[1] for item in message_data if isinstance(item, tuple)), None)
                if not raw_email:
                    result.failed += 1
                    continue

                msg = email.message_from_bytes(raw_email)
                email_date = MailImapService._parse_email_date(msg.get("Date"))
                if email_date and email_date <= scan_since:
                    continue
                result.processed += 1
                subject = MailImapService._decode_header_value(msg.get("Subject"))
                sender_name, sender_email = parseaddr(MailImapService._decode_header_value(msg.get("From")))
                sender_email = sender_email.lower()
                raw_body = MailImapService._extract_body(msg)
                attachment_texts = MailImapService._extract_attachment_texts(msg)
                if attachment_texts:
                    raw_body = f"{raw_body}\n\nТекст вложений:\n" + "\n\n".join(attachment_texts)
                attachment_diagnostics = [item for item in attachment_texts if "legacy .doc не распознан" in item]

                try:
                    outcome = await EmailLeadIntakeService.process_email(
                        session,
                        sender_email=sender_email,
                        sender_name=sender_name,
                        subject=subject,
                        raw_body=raw_body,
                        message_id=msg.get("Message-ID"),
                        email_date_raw=msg.get("Date"),
                        dry_run=dry_run,
                    )
                except Exception:
                    result.failed += 1
                    result.decisions.append(
                        EmailLeadDecision(
                            status="failed",
                            sender_email=sender_email,
                            subject=subject,
                            reason="processing_error",
                        )
                    )
                    continue

                if outcome.is_candidate:
                    result.candidates += 1
                if outcome.is_candidate or (dry_run and outcome.status == "filtered"):
                    result.decisions.append(
                        EmailLeadDecision(
                            status=outcome.status,
                            sender_email=sender_email,
                            subject=subject,
                            reason=outcome.reason,
                            lead_id=outcome.lead_id,
                            order_id=outcome.order_id,
                        )
                    )
                elif dry_run and attachment_diagnostics:
                    result.decisions.append(
                        EmailLeadDecision(
                            status=outcome.status,
                            sender_email=sender_email,
                            subject=subject,
                            reason="; ".join(attachment_diagnostics)[:300],
                        )
                    )
                if outcome.used_ai:
                    result.ai_checked += 1

                if outcome.status == "would_create":
                    result.would_create += 1
                elif outcome.status == "created":
                    result.created += 1
                    if outcome.order_id is not None:
                        result.order_ids.append(outcome.order_id)
                        result.created_order_ids.append(outcome.order_id)
                    if outcome.lead_id is not None:
                        result.lead_ids.append(outcome.lead_id)
                        result.created_lead_ids.append(outcome.lead_id)
                    if processed_folder:
                        client.copy(imap_id, processed_folder)
                        client.store(imap_id, "+FLAGS", "\\Deleted")
                elif outcome.status == "duplicate":
                    result.duplicates += 1
                    if outcome.order_id is not None:
                        result.order_ids.append(outcome.order_id)
                    if outcome.lead_id is not None:
                        result.lead_ids.append(outcome.lead_id)
                elif outcome.status == "rejected":
                    result.rejected += 1

            if processed_folder:
                client.expunge()
            if not dry_run:
                last_import_at = scan_started_at.isoformat(timespec="seconds")
                await MailImapService._set_global_config_value(
                    session,
                    MailImapService.EMAIL_LEAD_LAST_IMPORT_KEY,
                    last_import_at,
                    "Дата и время последней успешной проверки входящей почты на email-лиды.",
                )
                result.last_import_at = last_import_at
            return result
        finally:
            try:
                client.close()
            except Exception:
                pass
            client.logout()
