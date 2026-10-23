"""Behavioral mail regressions; external protocols are always stubbed."""
import email
from email.message import EmailMessage

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select

from core.config import settings
from mail_workspace_test_support import _actor, mail_db, mail_db_engine, smtp_settings
from models import IncomingMail, MailSyncCursor, OutgoingEmail
from schemas_mail import MailDraftCreatePayload, MailConfirmPayload, MailVersionPayload
from schemas_incoming_mail import IncomingMailSyncPayload
from services.incoming_mail_service import IncomingMailService as Inbox
from services.mail_imap_service import MailImapService
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.mail_smtp_service import MailSmtpService


from mail_reliability_test_support import FakeImap

@pytest.fixture
def imap(monkeypatch):
    client = FakeImap()
    async def connect(): return client
    async def close(client): pass
    monkeypatch.setattr(MailImapService, "_connect_async", connect)
    monkeypatch.setattr(MailImapService, "_close_async", close)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_FOLDER", "INBOX")
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "")
    return client


@pytest.mark.asyncio
async def test_sync_shows_recent_then_progresses_history_without_duplicate_fetch_and_replays_receipt(mail_db, imap):
    actor = await _actor(mail_db)
    payload = IncomingMailSyncPayload(limit=2)
    first = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-page-first-001")
    replay = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-page-first-001")
    assert replay.replayed and replay.value == first.value
    assert first.value.captured == 2 and first.value.has_more
    assert imap.fetched == [("INBOX", 4), ("INBOX", 5)]
    for n in (2, 3):
        last = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key=f"sync-page-next-{n:03}")
    assert last.value.captured == 1 and not last.value.has_more
    assert [uid for _, uid in imap.fetched] == [4, 5, 2, 3, 1]
    empty = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-page-empty-001")
    assert empty.value.processed == empty.value.captured == 0
    assert len(imap.fetched) == 5
    imap.validity = b"456"
    reset = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-validity-reset-001")
    assert reset.value.captured == 0 and reset.value.existing == 2
    cursor = (await mail_db.execute(select(MailSyncCursor))).scalar_one()
    assert cursor.uidvalidity == "456" and cursor.last_uid == 5


@pytest.mark.asyncio
async def test_sync_failure_rolls_back_cursor_and_imported_page_then_skips_oversized(mail_db, imap):
    actor = await _actor(mail_db)
    payload = IncomingMailSyncPayload(limit=3)
    imap.fail_uid = 4
    with pytest.raises(RuntimeError, match="fetch failed"):
        await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-failing-page-001")
    assert (await mail_db.execute(select(IncomingMail))).scalars().all() == []
    imap.fail_uid = None
    imap.oversized_uid = 4
    result = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="sync-failing-page-001")
    assert result.value.captured == 2 and result.value.skipped == 1
    cursor = (await mail_db.execute(select(MailSyncCursor))).scalar_one()
    assert cursor.last_uid == 5 and cursor.history_before_uid == 3


@pytest.mark.asyncio
async def test_sync_has_global_page_budget_and_independent_folder_cursors(mail_db, imap, monkeypatch):
    actor = await _actor(mail_db)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "Processed")
    imap.count = 2
    result = await Inbox.sync(mail_db, actor=actor, payload=IncomingMailSyncPayload(limit=3), idempotency_key="sync-two-folders-001")
    assert result.value.processed == 3 and result.value.has_more
    assert imap.fetched == [("INBOX", 1), ("INBOX", 2), ("Processed", 2)]
    assert result.value.captured == 2 and result.value.existing == 1


@pytest.mark.asyncio
async def test_reply_headers_survive_capture_edit_and_exact_transport(mail_db, monkeypatch):
    actor = await _actor(mail_db)
    incoming = EmailMessage()
    incoming["From"] = "no-reply@example.test"
    incoming["Reply-To"] = "Sales <sales@example.test>"
    incoming["Message-ID"] = "<parent@example.test>"
    incoming["References"] = "<root@example.test> invalid"
    incoming["In-Reply-To"] = "<root@example.test>"
    incoming.set_content("Full incoming body")
    row = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=incoming, raw_email=incoming.as_bytes())
    await mail_db.commit()
    detail = await Mail.get_message(mail_db, actor=actor, message_id=-row.id)
    assert detail.reply_to == ["sales@example.test"]
    assert detail.message_id == "<parent@example.test>" and detail.references == ["<root@example.test>"]
    draft = (await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(
        to=detail.reply_to, subject="Re: Test", body_text="Reply", in_reply_to=detail.message_id,
        references=[*detail.references, detail.message_id]), idempotency_key="thread-create-reply-001")).value
    await Mail.confirm(mail_db, actor=actor, draft_id=draft.id,
        payload=MailConfirmPayload(expected_version=draft.version, content_hash=draft.content_hash), idempotency_key="thread-confirm-reply-001")
    sent = []
    monkeypatch.setattr(MailSmtpService, "send_message", lambda message: sent.append(message))
    result = await Mail.send(mail_db, actor=actor, draft_id=draft.id,
        payload=MailVersionPayload(expected_version=draft.version), idempotency_key="thread-send-reply-001")
    assert result.value.status == "sent"
    assert sent[0]["To"] == "sales@example.test"
    assert sent[0]["In-Reply-To"] == "<parent@example.test>"
    assert sent[0]["References"] == "<root@example.test> <parent@example.test>"


@pytest.mark.parametrize("payload", [
    {"in_reply_to": "<ok@example.test>\r\nBcc: other@example.test"},
    {"references": ["not-a-message-id"]},
    {"references": ["<ok@example.test>\x00"]},
])
def test_thread_header_injection_is_rejected(payload):
    with pytest.raises(ValidationError):
        MailDraftCreatePayload(**payload)


@pytest.mark.asyncio
async def test_outbox_attachment_query_count_is_constant_and_detail_keeps_full_text(mail_db, mail_db_engine):
    actor = await _actor(mail_db)
    ids = []
    for i in range(4):
        created = (await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(body_text="x" * 1000), idempotency_key=f"batch-list-create-{i:03}")).value
        ids.append(created.id)
        await Mail.upload_attachment(mail_db, actor=actor, draft_id=created.id, expected_version=1,
            idempotency_key=f"batch-list-file-{i:03}", filename=f"{i}.txt", content=b"file")
    statements = []
    def track(conn, cursor, statement, parameters, context, executemany):
        if "SELECT" in statement.upper() and "FROM mail_attachment_snapshot" in statement:
            statements.append(statement)
    event.listen(mail_db_engine.sync_engine, "before_cursor_execute", track)
    try:
        result = await Mail.list_messages(mail_db, actor=actor, folder="drafts", limit=100)
    finally:
        event.remove(mail_db_engine.sync_engine, "before_cursor_execute", track)
    assert len(result.items) == 4 and len(statements) == 1
    assert all(len(item.body_text) == 300 and len(item.attachments) == 1 for item in result.items)
    detail = await Mail.get_message(mail_db, actor=actor, message_id=ids[0])
    assert len(detail.body_text) == 1000 and detail.content_hash


def test_unknown_sender_charset_does_not_block_import():
    raw = b'From: sender@example.test\nSubject: =?made-up-charset?b?SGVsbG8=?=\nContent-Type: text/plain; charset=made-up-charset\n\nHello'
    message = email.message_from_bytes(raw)
    assert MailImapService._extract_body(message) == "Hello"
    assert MailImapService._decode_header_value(message["Subject"]) == "Hello"
    assert MailImapService._decode_bytes(b"Hello\x00there", "bad-charset") == "Hello\ufffdthere"


@pytest.mark.asyncio
async def test_new_arrival_burst_precedes_history_and_never_skips_over_page_budget(mail_db, imap):
    actor = await _actor(mail_db)
    payload = IncomingMailSyncPayload(limit=2)
    await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="burst-initial-page-001")
    imap.count = 10
    for n in range(4):
        await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key=f"burst-forward-page-{n:03}")
    assert [uid for _, uid in imap.fetched] == [4, 5, 6, 7, 8, 9, 10, 3, 1, 2]
    assert len(set(imap.fetched)) == 10
    imap.count = 12
    result = await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="burst-followup-page-001")
    assert imap.fetched[-2:] == [("INBOX", 11), ("INBOX", 12)]
    assert not result.value.has_more


@pytest.mark.asyncio
async def test_second_folder_new_mail_precedes_first_folder_history_and_zero_budget_does_not_advance(mail_db, imap, monkeypatch):
    actor = await _actor(mail_db)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "Processed")
    imap.folder_counts = {"INBOX": 5, "Processed": 2}
    payload = IncomingMailSyncPayload(limit=2)
    await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="two-folder-priority-001")
    cursor = (await mail_db.execute(select(MailSyncCursor).where(MailSyncCursor.folder == "Processed"))).scalar_one()
    assert cursor.last_uid == 0 and cursor.history_before_uid is None
    await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="two-folder-priority-002")
    assert imap.fetched[-2:] == [("Processed", 1), ("Processed", 2)]
    imap.folder_counts["Processed"] = 3
    await Inbox.sync(mail_db, actor=actor, payload=payload, idempotency_key="two-folder-priority-003")
    assert imap.fetched[-2:] == [("Processed", 3), ("INBOX", 3)]


@pytest.mark.asyncio
async def test_legacy_invalid_message_id_still_allows_reply_without_threading(mail_db):
    actor = await _actor(mail_db)
    legacy = IncomingMail(tenant_id=1, source_key="legacy-raw-header", message_id="old malformed id\r\nBcc: stranger@example.test",
        sender_email="customer@example.test", subject="Old letter", body_text="Please reply")
    mail_db.add(legacy)
    await mail_db.commit()
    detail = await Mail.get_message(mail_db, actor=actor, message_id=-legacy.id)
    assert detail.message_id is None
    reply = await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(
        to=[detail.sender_email], subject="Re: Old letter", body_text="Our answer", in_reply_to=detail.message_id, references=detail.references),
        idempotency_key="legacy-raw-header-reply-001")
    assert reply.value.to == ["customer@example.test"] and reply.value.in_reply_to is None


@pytest.mark.asyncio
async def test_explicit_sync_hydrates_legacy_headers_without_replacing_saved_body(mail_db, imap):
    actor = await _actor(mail_db)
    incoming = EmailMessage()
    incoming["From"] = "no-reply@example.test"
    incoming["Reply-To"] = "sales@example.test"
    incoming["Message-ID"] = "<legacy-parent@example.test>"
    incoming["In-Reply-To"] = "<root@example.test>"
    incoming["References"] = "<root@example.test>"
    incoming.set_content("Original raw body")
    raw = incoming.as_bytes()
    legacy = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=incoming, raw_email=raw)
    legacy.reply_to, legacy.in_reply_to, legacy.references = [], None, []
    legacy.body_text = "Existing saved body is immutable"
    await mail_db.commit()
    imap.count, imap.raw_overrides = 1, {1: raw}
    result = await Inbox.sync(mail_db, actor=actor, payload=IncomingMailSyncPayload(limit=2), idempotency_key="hydrate-legacy-headers-001")
    assert result.value.captured == 0 and result.value.existing == 1
    detail = await Mail.get_message(mail_db, actor=actor, message_id=-legacy.id)
    assert detail.reply_to == ["sales@example.test"]
    assert detail.in_reply_to == "<root@example.test>" and detail.references == ["<root@example.test>"]
    assert detail.body_text == "Existing saved body is immutable"
