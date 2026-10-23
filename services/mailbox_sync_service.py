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
                      uidvalidity=validity, last_uid=0, history_before_uid=None)
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
            row.uidvalidity, row.last_uid, row.history_before_uid = validity, 0, None
        return row

    @staticmethod
    async def _uids(client, lower, upper=None):
        if lower > 4294967295 or (upper is not None and upper < lower):
            return []
        status, payload = await MailImapService._imap_call(
            client.uid, "SEARCH", None, "UID", f"{lower}:{upper if upper is not None else '*'}")
        if status != "OK":
            raise RuntimeError("IMAP search failed")
        # IMAP n:* may include the current maximum even when it is below n.
        return sorted({int(uid) for uid in (payload[0] or b"").split()
                       if lower <= int(uid) <= (upper or 4294967295)})

    @staticmethod
    async def _capture_page(session, scope, client, uids, result):
        for uid in uids:
            status, sizes = await MailImapService._imap_call(client.uid, "FETCH", str(uid).encode(), "(RFC822.SIZE)")
            size_raw = b" ".join(item if isinstance(item, bytes) else item[0]
                                 for item in sizes or [] if isinstance(item, (bytes, tuple)))
            found = re.search(rb"RFC822.SIZE\s+(\d+)", size_raw)
            if status != "OK":
                raise RuntimeError("IMAP size fetch failed")
            if found is None or int(found.group(1)) > MAX_INCOMING_BYTES:
                # Missing UID was expunged after SEARCH; oversized mail is explicit skip.
                result["skipped"] += 1
                continue
            status, data = await MailImapService._imap_call(client.uid, "FETCH", str(uid).encode(), "(BODY.PEEK[])")
            if status != "OK":
                raise RuntimeError("IMAP body fetch failed")
            raw = next((item[1] for item in data or [] if isinstance(item, tuple)), None)
            if not raw or len(raw) > MAX_INCOMING_BYTES:
                result["skipped"] += 1
                continue
            message = await asyncio.to_thread(email.message_from_bytes, raw)
            row, created = await IncomingMailService.capture_result(
                session, tenant_scope=scope, message=message, raw_email=raw)
            result["processed"] += 1
            result["captured"] += int(created)
            result["existing"] += int(row is not None and not created)

    @staticmethod
    async def _select(client, folder):
        status, _ = await MailImapService._imap_call(client.select, folder, readonly=True)
        if status != "OK":
            raise RuntimeError("IMAP folder unavailable")
        _, data = await MailImapService._imap_call(client.response, "UIDVALIDITY")
        validity = (data or [None])[0]
        if not isinstance(validity, bytes) or not validity.isdigit() or not 0 < int(validity) <= 4294967295:
            raise RuntimeError("IMAP UIDVALIDITY unavailable")
        return validity.decode()

    @classmethod
    async def _reselect(cls, client, folder, cursor):
        if await cls._select(client, folder) != cursor.uidvalidity:
            raise RuntimeError("IMAP UIDVALIDITY changed during synchronization")

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
            remaining, states = limit, []
            # Check forward progress in every folder before any history can use
            # the shared budget. Acquire cursor locks in stable configured order.
            for folder in folders:
                validity = await cls._select(client, folder)
                cursor = await cls._cursor(session, tenant_scope, folder, validity)
                bootstrap = cursor.history_before_uid is None
                forward = await cls._uids(client, 1 if bootstrap else cursor.last_uid + 1)
                states.append((folder, cursor, bootstrap, forward))
            for folder, cursor, bootstrap, forward in states:
                # Bootstrap shows recent mail immediately, retaining a separate
                # exclusive boundary for history. Later bursts advance ascending
                # so >limit new arrivals remain reachable on subsequent pages.
                selected = (forward[-remaining:] if remaining else []) if bootstrap else forward[:remaining]
                if selected:
                    await cls._reselect(client, folder, cursor)
                    await cls._capture_page(session, tenant_scope, client, selected, result)
                    cursor.last_uid = selected[-1]
                    if bootstrap:
                        cursor.history_before_uid = selected[0] if len(forward) > len(selected) else 0
                elif bootstrap and not forward:
                    cursor.history_before_uid = 0
                # Bootstrap with budget zero must retain its uninitialized state.
                remaining -= len(selected)
                result["has_more"] |= len(forward) > len(selected)
            for folder, cursor, _, _ in states:
                before = cursor.history_before_uid
                if before is None or before <= 1:
                    continue
                await cls._reselect(client, folder, cursor)
                history = await cls._uids(client, 1, before - 1)
                selected = history[-remaining:] if remaining else []
                await cls._capture_page(session, tenant_scope, client, selected, result)
                if selected:
                    cursor.history_before_uid = selected[0] if len(history) > len(selected) else 0
                elif not history:
                    cursor.history_before_uid = 0
                remaining -= len(selected)
                result["has_more"] |= len(history) > len(selected)
            # Both boundaries and captured messages commit with the command.
            await session.flush()
            return result
        finally:
            await MailImapService._close_async(client)
