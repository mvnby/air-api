"""Ordinary correspondence and order snapshots share mail without real delivery."""

import email
from email.message import EmailMessage

import pytest
from sqlalchemy import func, select

from core.config import settings
from mail_workspace_test_support import _actor, mail_db, mail_db_engine, smtp_settings
from models import Customer, Order, OrderDocument, OrderProposal
from models.incoming_mail import IncomingMail
from schemas_mail import MailConfirmPayload, MailVersionPayload
from schemas_order_mail import MailOrderDraftPayload
from services.incoming_mail_service import IncomingMailService as Inbox
from services.mail_imap_service import MailImapService
from services.mail_smtp_service import MailSmtpService, SmtpPartialAcceptanceError
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.order_mail_delivery_service import OrderMailDeliveryService


def _letter(body="Здравствуйте, запрос цены.", *, html=False):
    message = EmailMessage()
    message["Message-ID"] = "<ordinary-mail@example.test>"
    message["From"] = "Supplier <supplier@example.test>"
    message["To"] = "sales@example.test"
    message["Subject"] = "ebm-papst A2E200-AI38-01"
    message.set_content(body, subtype="html" if html else "plain")
    message.add_attachment(b"%PDF-1.4 approved fan data", maintype="application", subtype="pdf", filename="fan.pdf")
    return message


@pytest.mark.asyncio
async def test_capture_deduplicates_and_keeps_private_files_without_crm_entities(mail_db):
    actor = await _actor(mail_db)
    message = _letter()
    raw = message.as_bytes()
    saved = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=message, raw_email=raw)
    repeated = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=email.message_from_bytes(raw), raw_email=raw)
    await mail_db.commit()
    assert repeated.id == saved.id
    assert (await mail_db.execute(select(func.count()).select_from(IncomingMail))).scalar_one() == 1
    assert (await mail_db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
    assert (await mail_db.execute(select(func.count()).select_from(Customer))).scalar_one() == 0
    detail = await Mail.get_message(mail_db, actor=actor, message_id=-saved.id)
    assert detail.id < 0 and detail.folder == "inbox" and detail.status == "received"
    assert detail.to == ["sales@example.test"]
    assert detail.attachments[0].available
    file = await Inbox.read_attachment(mail_db, actor=actor, email_id=detail.id, attachment_id=detail.attachments[0].id)
    assert file.content == b"%PDF-1.4 approved fan data"
    missing = await Mail.list_messages(mail_db, actor=actor, folder="inbox", q="unrelated")
    assert missing.total == 0
    found = await Mail.list_messages(mail_db, actor=actor, folder="inbox", q="A2E200")
    assert found.total == 1 and found.items[0].id == detail.id
    with pytest.raises(LookupError):
        await Inbox.read_attachment(mail_db, actor=actor, email_id=detail.id, attachment_id=999)


@pytest.mark.asyncio
async def test_html_mail_is_plain_data_and_reused_message_id_cannot_overwrite_history(mail_db):
    actor = await _actor(mail_db)
    first = _letter('<script>steal()</script><p>Цена 100</p><img src="https://tracker.test/x">', html=True)
    saved = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=first, raw_email=first.as_bytes())
    second = _letter("Другое содержимое с тем же Message-ID")
    other = await Inbox.capture(mail_db, tenant_scope=actor.tenant_scope, message=second, raw_email=second.as_bytes())
    await mail_db.commit()
    assert saved.id != other.id
    detail = await Inbox.get_message(mail_db, actor=actor, email_id=-saved.id)
    assert detail.body_text == "Цена 100"
    assert "steal" not in detail.body_text and "tracker" not in detail.body_text


@pytest.mark.asyncio
async def test_mailbox_sync_reuses_imap_readonly_and_does_not_classify(mail_db, monkeypatch):
    actor = await _actor(mail_db)
    raw = _letter().as_bytes()
    calls = []
    class Client:
        def select(self, folder, readonly=False):
            calls.append(("select", readonly))
            return "OK", []
        def uid(self, operation, *args):
            calls.append((operation, args))
            if operation == "SEARCH":
                return "OK", [b"11"]
            if args[-1] == "(RFC822.SIZE)":
                return "OK", [f"11 (RFC822.SIZE {len(raw)})".encode()]
            return "OK", [(b"11 (BODY[])", raw)]
    async def connect():
        return Client()
    async def close(_):
        pass
    def classify(*args, **kwargs):
        pytest.fail("Ordinary mailbox sync must not classify into CRM")
    monkeypatch.setattr(MailImapService, "_connect_async", connect)
    monkeypatch.setattr(MailImapService, "_close_async", close)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "")
    monkeypatch.setattr("services.email_lead_intake_service.EmailLeadIntakeService.process_email", classify)
    result = await MailImapService.sync_mailbox(mail_db, tenant_scope=actor.tenant_scope, limit=50)
    await mail_db.commit()
    assert result == {"processed": 1, "captured": 1, "skipped": 0}
    assert calls[0] == ("select", True)
    assert calls[-1][1][-1] == "(BODY.PEEK[])"


@pytest.mark.asyncio
async def test_order_draft_snapshots_once_then_shared_send_preserves_order_lifecycle(mail_db, monkeypatch):
    actor = await _actor(mail_db)
    order = Order(tenant_id=1, storefront_id=1, status="negotiation", proposal_status="draft")
    mail_db.add(order)
    await mail_db.flush()
    proposal = OrderProposal(order_id=order.id, name="Fan", is_selected=True, status="ready_to_send")
    mail_db.add(proposal)
    await mail_db.flush()
    document = OrderDocument(order_id=order.id, proposal_id=proposal.id, doc_type="offer", number="FAN-1")
    mail_db.add(document)
    await mail_db.commit()
    downloads = []
    async def download(session, document_id, **kwargs):
        downloads.append(document_id)
        return b"%PDF original approved version" if len(downloads) == 1 else b"%PDF changed version", "fan.pdf"
    monkeypatch.setattr("services.mail_smtp_service.DocumentService.get_download_stream", download)
    payload = MailOrderDraftPayload(to_email="supplier@example.test", subject="Fan", body_text="Please quote", document_ids=[document.id])
    created = await OrderMailDeliveryService.create_draft(mail_db, actor=actor, order_id=order.id,
        payload=payload, idempotency_key="order-fan-draft-001")
    repeated = await OrderMailDeliveryService.create_draft(mail_db, actor=actor, order_id=order.id,
        payload=payload, idempotency_key="order-fan-draft-001")
    assert repeated.replayed and repeated.value.id == created.value.id and downloads == [document.id]
    assert order.proposal_status == "draft" and proposal.status == "ready_to_send"
    sent = []
    monkeypatch.setattr(MailSmtpService, "send_message", lambda message: sent.append(message))
    draft = created.value
    await Mail.confirm(mail_db, actor=actor, draft_id=draft.id,
        payload=MailConfirmPayload(expected_version=draft.version, content_hash=draft.content_hash), idempotency_key="order-fan-confirm-001")
    result = await Mail.send(mail_db, actor=actor, draft_id=draft.id,
        payload=MailVersionPayload(expected_version=draft.version), idempotency_key="order-fan-send-001")
    assert result.value.status == "sent" and len(sent) == 1
    assert list(sent[0].iter_attachments())[0].get_payload(decode=True) == b"%PDF original approved version"
    await mail_db.refresh(order)
    await mail_db.refresh(proposal)
    assert order.proposal_status == proposal.status == "sent"
    empty = await OrderMailDeliveryService.create_draft(mail_db, actor=actor, order_id=order.id,
        payload=MailOrderDraftPayload(), idempotency_key="order-empty-draft-001")
    assert empty.value.status == "draft" and empty.value.to == []


@pytest.mark.asyncio
async def test_partial_smtp_acceptance_is_unknown_and_does_not_repeat(mail_db, monkeypatch):
    from mail_workspace_test_support import _ready
    actor = await _actor(mail_db)
    draft = await _ready(mail_db, actor, "partial", attachment=False)
    attempts = []
    def transport(message):
        attempts.append(message)
        raise SmtpPartialAcceptanceError("A recipient refused but another accepted")
    monkeypatch.setattr(MailSmtpService, "send_message", transport)
    first = await Mail.send(mail_db, actor=actor, draft_id=draft.id,
        payload=MailVersionPayload(expected_version=draft.version), idempotency_key="partial-send-001")
    second = await Mail.send(mail_db, actor=actor, draft_id=draft.id,
        payload=MailVersionPayload(expected_version=draft.version), idempotency_key="partial-send-002")
    assert first.value.status == second.value.status == "unknown" and len(attempts) == 1
