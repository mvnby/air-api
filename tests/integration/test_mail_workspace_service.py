"""Exact-version approval, private bytes and the durable SMTP send fence."""

import asyncio
import importlib.util
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OutgoingEmail
from models.command_audit import CommandAuditEvent
from schemas_mail import MailDraftUpdatePayload, MailVersionPayload
from services.mail_smtp_service import MailSmtpService
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.mail_workspace_access import MailStateConflictError

from mail_workspace_test_support import smtp_settings, _actor, _ready

@pytest.mark.asyncio
async def test_parallel_different_keys_send_one_committed_snapshot(db_engine, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    sent = []
    def transport(message):
        sent.append(message)
        entered.set()
        assert release.wait(8), "Test did not release transport"
    monkeypatch.setattr(MailSmtpService, "send_message", staticmethod(transport))
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
        message = await _ready(setup, actor, "parallel")
    async with AsyncSession(db_engine, expire_on_commit=False) as first, AsyncSession(db_engine, expire_on_commit=False) as second:
        sending = asyncio.create_task(Mail.send(first, actor=actor, draft_id=message.id,
            payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-parallel-first-001"))
        try:
            assert await asyncio.to_thread(entered.wait, 4), "Transport was not reached"
            # Another physical connection sees a durable claim while SMTP has not completed.
            observed = await second.get(OutgoingEmail, message.id)
            assert observed.status == "sending" and observed.confirmed_version == message.version
            duplicate = await Mail.send(second, actor=actor, draft_id=message.id,
                payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-parallel-second-001")
            assert duplicate.value.status == "sending"
        finally:
            release.set()
        result = await sending
        assert result.value.status == "sent" and result.value.sent_at is not None
        assert len(sent) == 1
        assert sent[0]["To"] == "supplier@example.test"
        assert sent[0].get_body(preferencelist=("plain",)).get_content().strip() == message.body_text
        assert list(sent[0].iter_attachments())[0].get_payload(decode=True) == b"%PDF-1.4 fixed attachment"
        replay = await Mail.send(first, actor=replace(actor, channel="chatgpt"), draft_id=message.id,
            payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-parallel-first-001")
        assert replay.replayed and replay.value.status == "sent" and len(sent) == 1
        fresh_key = await Mail.send(first, actor=actor, draft_id=message.id,
            payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-parallel-third-001")
        assert fresh_key.value.status == "sent" and len(sent) == 1
        with pytest.raises(MailStateConflictError):
            await Mail.update_draft(first, actor=actor, draft_id=message.id,
                payload=MailDraftUpdatePayload(expected_version=message.version, body_text="overwrite"), idempotency_key="mail-immutable-update-001")
        with pytest.raises(MailStateConflictError):
            await Mail.delete_draft(first, actor=actor, draft_id=message.id,
                payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-immutable-delete-001")
        operations = (await first.execute(select(CommandAuditEvent.operation))).scalars().all()
        assert "mail.draft.send" in operations and "mail.delivery.finish" in operations

@pytest.mark.asyncio
async def test_mail_migration_roundtrip_preserves_existing_history(db_engine):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/t1090mail01_add_mail_workspace.py"
    spec = importlib.util.spec_from_file_location("mail_workspace_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def check(connection):
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        identifier = connection.execute(text("INSERT INTO outgoing_email(status,recipient_email,subject,body_text,created_at,updated_at) VALUES('sent','legacy@example.test','Existing history','History body',now(),now()) RETURNING id")).scalar_one()
        migration.upgrade()
        record = connection.execute(text("SELECT status,subject,body_text,version,cc_emails,bcc_emails FROM outgoing_email WHERE id=:id"), {"id": identifier}).one()
        assert tuple(record) == ("sent", "Existing history", "History body", 1, [], [])
        assert {"mail_attachment_snapshot", "incoming_mail", "incoming_mail_attachment"} <= set(inspect(connection).get_table_names())
        migration.downgrade()
        assert connection.execute(text("SELECT subject FROM outgoing_email WHERE id=:id"), {"id": identifier}).scalar_one() == "Existing history"
        migration.upgrade()
    async with db_engine.begin() as connection:
        await connection.run_sync(check)
