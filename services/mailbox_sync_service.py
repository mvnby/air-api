"""Transactional per-folder IMAP progress; SMTP and CRM intake are never involved."""

import asyncio
import email
import re

from sqlalchemy import select
from models.incoming_mail import MailSyncCursor
from services.incoming_mail_service import IncomingMailService, MAX_INCOMING_BYTES
from services.mail_imap_service import MailImapService
from core.config import settings


class MailboxSyncService:
    @staticmethod
    async def _cursor(session, scope, folder, validity):
        values = dict(tenant_id=scope.tenant_id, account_id="system", folder=folder,
                      uidvalidity=validity, last_uid=0)
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        await session.execute(insert(MailSyncCursor).values(**values).on_conflict_do_nothing(
            index_elements=["tenant_id", "account_id", "folder"]))
        row = (await session.execute(select(MailSyncCursor).where(
            MailSyncCursor.tenant_id == scope.tenant_id, MailSyncCursor.account_id == "system",
            MailSyncCursor.folder == folder).with_for_update().execution_options(populate_existing=True))).scalar_one()
        if row.uidvalidity != validity:
            row.uidvalidity, row.last_uid = validity, 0
        return row

    @classmethod
    async def sync(cls, session, *, tenant_scope, limit=50):
        if not tenant_scope.is_system:
            raise PermissionError("Почтовый аккаунт компании не настроен")
        if not 1 <= limit <= 100:
            raise ValueError("Размер страницы должен быть от 1 до 100")
        result = dict(processed=0, captured=0, skipped=0, existing=0, has_more=False)
        client = await MailImapService._connect_async()
        try:
            folders = dict.fromkeys(filter(None, (
                settings.MAIL_IMAP_LEAD_FOLDER or "INBOX", settings.MAIL_IMAP_LEAD_PROCESSED_FOLDER)))
            remaining = limit
            for folder in folders:
                status, _ = await MailImapService._imap_call(client.select, folder, readonly=True)
                if status != "OK":
                    raise RuntimeError("IMAP folder unavailable")
                _, validity_data = await MailImapService._imap_call(client.response, "UIDVALIDITY")
                validity = (validity_data or [None])[0]
                if not isinstance(validity, bytes) or not validity.isdigit() or not 0 < int(validity) <= 4294967295:
                    raise RuntimeError("IMAP UIDVALIDITY unavailable")
                cursor = await cls._cursor(session, tenant_scope, folder, validity.decode())
                status, payload = await MailImapService._imap_call(client.uid, "SEARCH", None, "UID", f"{cursor.last_uid + 1}:*")
                if status != "OK":
                    raise RuntimeError("IMAP search failed")
                uids = sorted({int(uid) for uid in (payload[0] or b"").split() if int(uid) > cursor.last_uid})
                result["has_more"] |= len(uids) > remaining
                for uid in uids[:remaining]:
                    remaining -= 1
                    status, sizes = await MailImapService._imap_call(client.uid, "FETCH", str(uid).encode(), "(RFC822.SIZE)")
                    size_raw = b" ".join(item if isinstance(item, bytes) else item[0]
                                         for item in sizes or [] if isinstance(item, (bytes, tuple)))
                    found = re.search(rb"RFC822.SIZE\s+(\d+)", size_raw)
                    if status != "OK":
                        raise RuntimeError("IMAP size fetch failed")
                    if found is None:
                        # UID was expunged after SEARCH; no bytes remain to import.
                        result["skipped"] += 1
                    elif int(found.group(1)) > MAX_INCOMING_BYTES:
                        result["skipped"] += 1
                    else:
                        status, data = await MailImapService._imap_call(client.uid, "FETCH", str(uid).encode(), "(BODY.PEEK[])")
                        if status != "OK":
                            raise RuntimeError("IMAP body fetch failed")
                        raw = next((item[1] for item in data or [] if isinstance(item, tuple)), None)
                        if not raw or len(raw) > MAX_INCOMING_BYTES:
                            result["skipped"] += 1
                        else:
                            message = await asyncio.to_thread(email.message_from_bytes, raw)
                            row, created = await IncomingMailService.capture_result(
                                session, tenant_scope=tenant_scope, message=message, raw_email=raw)
                            result["processed"] += 1
                            result["captured"] += int(created)
                            result["existing"] += int(row is not None and not created)
                    # Cursor and saved message commit together in the enclosing command.
                    cursor.last_uid = uid
                    await session.flush()
            return result
        finally:
            await MailImapService._close_async(client)
