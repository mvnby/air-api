"""Delivery checkpoints and retry behavior without a live mailbox or database."""

import asyncio
import json
from datetime import datetime
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.config import settings
import services.mail_imap_service as imap_module
from services.email_lead_import_job_service import EmailLeadImportJobService
from services.email_lead_intake_service import EmailLeadIntakeService, EmailLeadProcessResult
from services.incoming_mail_service import IncomingMailService
from services.mail_imap_service import MailImapService
from services.scheduler_service import SchedulerService
from services.tenant_scope_service import TenantScope


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
def mailbox(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 12, 12)

    message = EmailMessage()
    message["From"] = "client@example.test"
    message["Subject"] = "Цена кондиционера"
    message["Date"] = "Wed, 11 Nov 2026 09:00:00 +0300"
    message["Message-ID"] = "<retry@example.test>"
    message.set_content("Просим цену кондиционера.")
    state = SimpleNamespace(
        checkpoint=datetime(2026, 11, 12, 10), message=message,
        delivered_at=datetime(2026, 11, 12, 11), fetch_failed=False,
    )

    class Imap:
        def select(self, *_args, **_kwargs):
            return "OK", []

        def search(self, *_args):
            return "OK", [b"1"]

        def fetch(self, _id, query):
            assert query == "(RFC822 INTERNALDATE)"
            if state.fetch_failed:
                return "NO", []
            metadata = b"1 RFC822"
            if state.delivered_at is not None:
                stamp = state.delivered_at.astimezone().strftime("%d-%b-%Y %H:%M:%S %z")
                metadata += f' INTERNALDATE "{stamp}"'.encode()
            return "OK", [(metadata, state.message.as_bytes())]

        def close(self):
            pass

        def logout(self):
            pass

    async def scan(_session):
        return state.checkpoint

    async def set_checkpoint(_session, _key, value, _description):
        state.checkpoint = datetime.fromisoformat(value)

    monkeypatch.setattr(imap_module, "datetime", Clock)
    monkeypatch.setattr(MailImapService, "_connect", Imap)
    monkeypatch.setattr(MailImapService, "_email_lead_scan_since", scan)
    monkeypatch.setattr(MailImapService, "_set_global_config_value", set_checkpoint)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "")
    monkeypatch.setattr(IncomingMailService, "capture", AsyncMock(return_value=None))
    state.session = SimpleNamespace(is_active=True, commit=AsyncMock())

    async def rollback():
        state.session.is_active = True

    state.session.rollback = AsyncMock(side_effect=rollback)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["ai", "fetch", "transaction"])
async def test_failed_delivery_retries_without_advancing_checkpoint(mailbox, monkeypatch, failure, caplog):
    calls = 0

    async def process(_session, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1 and failure != "fetch":
            if failure == "transaction":
                mailbox.session.is_active = False
            raise TimeoutError("private email content must not be logged")
        return EmailLeadProcessResult(status="created", is_candidate=True, used_ai=True)

    monkeypatch.setattr(EmailLeadIntakeService, "process_email", process)
    previous = mailbox.checkpoint
    mailbox.fetch_failed = failure == "fetch"
    first = await MailImapService.import_email_leads(mailbox.session, tenant_scope=SCOPE)
    assert first.failed == 1
    assert first.last_import_at is None
    assert mailbox.checkpoint == previous
    mailbox.session.commit.assert_awaited_once()
    assert "private email content" not in caplog.text
    if failure == "transaction":
        mailbox.session.rollback.assert_awaited_once()
    else:
        mailbox.session.rollback.assert_not_awaited()
    mailbox.fetch_failed = False
    if failure == "fetch":
        # The first fetch never reached the classifier.
        calls = 1
    second = await MailImapService.import_email_leads(mailbox.session, tenant_scope=SCOPE)
    assert second.created == 1
    assert second.failed == 0
    assert mailbox.checkpoint > previous


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered_at,expected", [
    (datetime(2026, 11, 12, 11), 1),
    (datetime(2026, 11, 12, 10), 1),
    (datetime(2026, 11, 12, 9), 0),
    (None, 1),
])
async def test_delivery_timestamp_controls_scan_not_sender_date(mailbox, monkeypatch, delivered_at, expected):
    mailbox.delivered_at = delivered_at
    process = AsyncMock(return_value=EmailLeadProcessResult(status="filtered", is_candidate=False))
    monkeypatch.setattr(EmailLeadIntakeService, "process_email", process)
    result = await MailImapService.import_email_leads(mailbox.session, tenant_scope=SCOPE)
    assert result.processed == expected
    assert process.await_count == expected


@pytest.mark.asyncio
async def test_attachment_candidate_survives_long_email_body(mailbox, monkeypatch):
    mailbox.message.replace_header("Subject", "Документы")
    mailbox.message.set_content("Нейтральный текст. " * 400)
    mailbox.message.add_attachment(
        b"ignored", maintype="application", subtype="octet-stream", filename="request.txt",
    )
    extracted = "Вложение request.txt:\nПросим цену кондиционера и монтаж."
    monkeypatch.setattr(MailImapService, "_extract_attachment_texts", lambda _msg: [extracted])
    monkeypatch.setattr(EmailLeadIntakeService, "_find_duplicate_order", AsyncMock(return_value=None))
    completion = AsyncMock(return_value='{"is_potential_order": true}')
    monkeypatch.setattr(EmailLeadIntakeService, "_request_completion", completion)
    result = await MailImapService.import_email_leads(mailbox.session, tenant_scope=SCOPE, dry_run=True)
    assert result.would_create == 1
    completion.assert_awaited_once()
    prompt = completion.await_args.args[0]
    ai_body = json.loads(prompt.split("Входные данные:\n", 1)[1])["body"]
    assert "Просим цену кондиционера и монтаж." in ai_body
    assert len(ai_body) <= 5000


def test_attachment_prefilter_still_rejects_unrelated_files(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_KEYWORDS", "")
    assert not EmailLeadIntakeService.looks_like_lead_candidate(
        sender_email="sender@example.test", subject="Документы", raw_body="Нейтральный текст. " * 400,
        attachment_texts=("Вложение report.txt: Годовой финансовый отчёт.",),
    )


@pytest.mark.asyncio
async def test_email_scheduler_recovers_after_interval_lookup_failure(monkeypatch):
    scheduler = SchedulerService()
    reads = 0
    sleeps = []

    async def config(key, default):
        nonlocal reads
        reads += 1
        if reads == 1:
            raise ConnectionError("temporary database outage")
        return "true" if key == "mail_lead_auto_import_enabled" else "3"

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise asyncio.CancelledError()

    run = AsyncMock(return_value=SimpleNamespace(result=None, already_running=False, status="completed", error=None))
    monkeypatch.setattr(scheduler, "_get_global_config_value", config)
    monkeypatch.setattr(settings, "MAIL_IMAP_USERNAME", "test-user")
    monkeypatch.setattr(settings, "MAIL_IMAP_PASSWORD", "test-password")
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_IMPORT_INTERVAL_MINUTES", 2)
    monkeypatch.setattr(EmailLeadImportJobService, "run_scheduled_import", run)
    monkeypatch.setattr("services.scheduler_service.asyncio.sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await scheduler._email_lead_import_loop()
    run.assert_awaited_once()
    assert sleeps == [120, 180]
