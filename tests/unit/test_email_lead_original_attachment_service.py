from datetime import date
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from models import LeadSource
from services.email_lead_original_attachment_service import EmailLeadOriginalAttachmentService


@pytest.mark.asyncio
async def test_original_email_lookup_uses_order_identity_and_retains_mime_bytes(monkeypatch):
    source = EmailMessage()
    source["Message-ID"] = "<verified@example.test>"
    source["From"] = "customer@example.test"
    source["Subject"] = "Договор на обслуживание"
    source.set_content("Направляем договор")
    original = b"original-doc-bytes"
    source.add_attachment(original, maintype="application", subtype="msword", filename="contract.doc")
    order = SimpleNamespace(lead_source=LeadSource.EMAIL, technical_meta={
        "email_source_message_id": "<verified@example.test>",
        "email_sender": "customer@example.test",
        "email_subject": "Договор на обслуживание",
        "email_date": "2026-09-29T11:28",
    })
    captured = {}

    async def get_order(_session, _order_id, *, tenant_scope):
        assert tenant_scope == "allowed-scope"
        return order

    async def find_message(message_id, sender, subject, email_date):
        captured.update(message_id=message_id, sender=sender, subject=subject, email_date=email_date)
        return source

    monkeypatch.setattr("services.email_lead_original_attachment_service.TenantEntityAccessService.get_order", get_order)
    monkeypatch.setattr(EmailLeadOriginalAttachmentService, "_find_message", find_message)

    files = await EmailLeadOriginalAttachmentService.load(None, order_id=456, tenant_scope="allowed-scope")

    assert captured["email_date"] == date(2026, 9, 29)
    assert captured["message_id"] == "<verified@example.test>"
    assert [(item.filename, item.content) for item in files] == [("contract.doc", original)]


@pytest.mark.asyncio
async def test_original_lookup_rejects_non_email_order_before_imap(monkeypatch):
    async def get_order(*_args, **_kwargs):
        return SimpleNamespace(lead_source=LeadSource.SITE, technical_meta={})

    async def forbidden(*_args):
        raise AssertionError("IMAP should not be called")

    monkeypatch.setattr("services.email_lead_original_attachment_service.TenantEntityAccessService.get_order", get_order)
    monkeypatch.setattr(EmailLeadOriginalAttachmentService, "_find_message", forbidden)

    assert await EmailLeadOriginalAttachmentService.load(None, order_id=7, tenant_scope="allowed-scope") is None


@pytest.mark.asyncio
async def test_imap_lookup_reads_full_mime_only_after_matching_headers(monkeypatch):
    class FakeClient:
        full_fetches = []

        def select(self, _folder, *, readonly):
            assert readonly is True
            return "OK", [b"2"]

        def uid(self, action, uid_or_none, *args):
            if action == "SEARCH":
                assert args == ("SINCE", "28-Sep-2026", "BEFORE", "01-Oct-2026")
                return "OK", [b"1 2"]
            if args == ("(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT)])",):
                message_id = "<target@example.test>" if uid_or_none == b"1" else "<other@example.test>"
                return "OK", [(b"", f"Message-ID: {message_id}\r\nFrom: sender@example.test\r\nSubject: Contract\r\n\r\n".encode())]
            self.full_fetches.append(uid_or_none)
            return "OK", [(b"", b"Message-ID: <target@example.test>\r\nFrom: sender@example.test\r\nSubject: Contract\r\n\r\nbody")]

    client = FakeClient()

    async def connect():
        return client

    async def call(method, *args, **kwargs):
        return method(*args, **kwargs)

    async def close(_client):
        return None

    monkeypatch.setattr("services.email_lead_original_attachment_service.MailImapService._connect_async", connect)
    monkeypatch.setattr("services.email_lead_original_attachment_service.MailImapService._imap_call", call)
    monkeypatch.setattr("services.email_lead_original_attachment_service.MailImapService._close_async", close)
    monkeypatch.setattr("services.email_lead_original_attachment_service.settings.MAIL_IMAP_LEAD_FOLDER", "INBOX")
    monkeypatch.setattr("services.email_lead_original_attachment_service.settings.MAIL_IMAP_LEAD_PROCESSED_FOLDER", "")

    found = await EmailLeadOriginalAttachmentService._find_message(
        "<target@example.test>", "sender@example.test", "Contract", date(2026, 9, 29),
    )

    assert found is not None and found.get("Message-ID") == "<target@example.test>"
    assert client.full_fetches == [b"1"]
