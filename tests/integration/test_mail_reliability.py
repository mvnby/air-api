"""Physical-PostgreSQL serialization, recovery and additive migration proofs."""
import asyncio
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from mail_workspace_test_support import _actor, smtp_settings
from mail_reliability_test_support import FakeImap
from models import IncomingMail, MailSyncCursor, DocumentLegalEntity, Order, OrderDocument, OrderProposal, OutgoingEmail, TenantMembership
from schemas_incoming_mail import IncomingMailSyncPayload
from schemas_mail import MailConfirmPayload, MailVersionPayload
from schemas_order_mail import MailOrderDraftPayload
from services.incoming_mail_service import IncomingMailService as Inbox
from services.mail_imap_service import MailImapService
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.mail_smtp_service import MailSmtpService
from services.order_mail_delivery_service import OrderMailDeliveryService


@pytest.mark.asyncio
async def test_concurrent_syncs_serialize_one_folder_cursor(db_engine, monkeypatch):
    fetched = []
    async def connect():
        client = FakeImap(count=4)
        client.fetched = fetched
        return client
    async def close(client): pass
    monkeypatch.setattr(MailImapService, "_connect_async", connect)
    monkeypatch.setattr(MailImapService, "_close_async", close)
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_FOLDER", "INBOX")
    monkeypatch.setattr(settings, "MAIL_IMAP_LEAD_PROCESSED_FOLDER", "")
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
    async def sync(key):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await Inbox.sync(session, actor=actor, payload=IncomingMailSyncPayload(limit=2), idempotency_key=key)
    outcomes = await asyncio.gather(sync("concurrent-sync-first-001"), sync("concurrent-sync-other-001"))
    assert sum(item.value.captured for item in outcomes) == 4
    assert fetched == [("INBOX", 3), ("INBOX", 4), ("INBOX", 1), ("INBOX", 2)]
    async with AsyncSession(db_engine) as session:
        assert (await session.execute(select(MailSyncCursor.last_uid))).scalar_one() == 4
        assert len((await session.execute(select(IncomingMail))).scalars().all()) == 4


async def ready_order(session, actor, monkeypatch):
    order = Order(tenant_id=1, storefront_id=1, status="negotiation", proposal_status="draft")
    session.add(order)
    await session.flush()
    proposal = OrderProposal(order_id=order.id, name="Offer", is_selected=True, status="ready_to_send")
    session.add(proposal)
    await session.flush()
    issuer = DocumentLegalEntity(tenant_id=1, slug="mail-issuer", display_name="Mail issuer")
    session.add(issuer)
    await session.flush()
    document = OrderDocument(tenant_id=1, legal_entity_id=issuer.id, internal_reference="mail-1", order_id=order.id, proposal_id=proposal.id,
        doc_type="offer", number="MAIL-1", status="issued", snapshot_version=1)
    session.add(document)
    await session.commit()
    async def download(*args, **kwargs): return b"%PDF fixed bytes", "offer.pdf"
    monkeypatch.setattr("services.mail_smtp_service.DocumentService.get_download_stream", download)
    message = (await OrderMailDeliveryService.create_draft(session, actor=actor, order_id=order.id,
        payload=MailOrderDraftPayload(to_email="customer@example.test", subject="Offer", body_text="Approved offer", document_ids=[document.id]),
        idempotency_key="recovery-order-create-001")).value
    await Mail.confirm(session, actor=actor, draft_id=message.id,
        payload=MailConfirmPayload(expected_version=message.version, content_hash=message.content_hash), idempotency_key="recovery-order-confirm-001")
    return message, order.id, proposal.id, document.id


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", ["replay", "another_member"])
async def test_projection_failure_rolls_back_lifecycle_and_recovers_without_smtp(db_engine, monkeypatch, recovery):
    sent = []
    monkeypatch.setattr(MailSmtpService, "send_message", lambda message: sent.append(message))
    real_after_sent = OrderMailDeliveryService.after_sent
    attempts = []
    async def flaky(session, **kwargs):
        attempts.append(kwargs["commit"])
        await real_after_sent(session, **kwargs)
        if len(attempts) == 1:
            raise RuntimeError("Injected crash after lifecycle flush")
    monkeypatch.setattr(OrderMailDeliveryService, "after_sent", flaky)
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        actor = await _actor(session)
        message, order_id, proposal_id, document_id = await ready_order(session, actor, monkeypatch)
        payload = MailVersionPayload(expected_version=message.version)
        first = await Mail.send(session, actor=actor, draft_id=message.id, payload=payload, idempotency_key="recovery-send-once-001")
        assert first.value.status == "sent" and first.value.delivery_projection_pending
        assert len(sent) == 1
        # All lifecycle changes and the obligation clear were rolled back together.
        assert (await session.get(Order, order_id)).proposal_status == "draft"
        assert (await session.get(OrderProposal, proposal_id)).status == "ready_to_send"
        assert (await session.get(OrderDocument, document_id)).status == "issued"
        if recovery == "another_member":
            replacement = await _actor(session, username="replacement-manager")
            membership = (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == actor.staff_user_id))).scalar_one()
            membership.status = "disabled"
            await session.commit()
            with pytest.raises(PermissionError):
                await Mail.get_message(session, actor=actor, message_id=message.id)
            result = await Mail.get_message(session, actor=replacement, message_id=message.id)
        else:
            repeated = await Mail.send(session, actor=actor, draft_id=message.id, payload=payload, idempotency_key="recovery-send-once-001")
            assert repeated.replayed
            result = repeated.value
        assert result.status == "sent" and not result.delivery_projection_pending
        assert len(sent) == 1 and attempts == [False, False]
        assert (await session.get(Order, order_id)).proposal_status == "sent"
        assert (await session.get(OrderProposal, proposal_id)).status == "sent"
        document = await session.get(OrderDocument, document_id)
        assert document.status == "sent" and document.sent_at is not None


@pytest.mark.asyncio
async def test_pending_projection_is_serialized_between_readers(db_engine, monkeypatch):
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
        message, order_id, _, _ = await ready_order(setup, actor, monkeypatch)
        row = await setup.get(OutgoingEmail, message.id)
        row.status, row.delivery_projection_pending = "sent", True
        from datetime import datetime
        row.sent_at = datetime.now()
        await setup.commit()
    real = OrderMailDeliveryService.after_sent
    attempts = []
    async def observe(session, **kwargs):
        attempts.append(kwargs["email"].id)
        await asyncio.sleep(0)
        await real(session, **kwargs)
    monkeypatch.setattr(OrderMailDeliveryService, "after_sent", observe)
    async def read():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await Mail.get_message(session, actor=actor, message_id=message.id)
    result = await asyncio.gather(read(), read())
    assert all(not item.delivery_projection_pending for item in result)
    assert attempts == [message.id]


@pytest.mark.asyncio
async def test_reliability_migration_roundtrip_preserves_existing_mail(db_engine):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/mail20261023rel01_mail_reliability.py"
    spec = importlib.util.spec_from_file_location("mail_reliability_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def check(connection):
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        identifier = connection.execute(text("INSERT INTO outgoing_email(status,recipient_email,subject,body_text,created_at,updated_at) VALUES('sent','old@example.test','Saved','Original body',now(),now()) RETURNING id")).scalar_one()
        migration.upgrade()
        row = connection.execute(text('SELECT status,body_text,in_reply_to,"references",delivery_projection_pending FROM outgoing_email WHERE id=:id'), {"id": identifier}).one()
        assert tuple(row) == ("sent", "Original body", None, [], False)
        assert connection.execute(text("SELECT count(*) FROM mail_sync_cursor")).scalar_one() == 0
        migration.downgrade()
        migration.upgrade()
    async with db_engine.begin() as connection:
        await connection.run_sync(check)


@pytest.mark.asyncio
async def test_delayed_projection_preserves_later_customer_decision(db_engine, monkeypatch):
    from datetime import datetime, timedelta
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        actor = await _actor(session)
        message, order_id, proposal_id, _ = await ready_order(session, actor, monkeypatch)
        row = await session.get(OutgoingEmail, message.id)
        row.status, row.delivery_projection_pending = "sent", True
        row.sent_at = datetime.now() - timedelta(days=1)
        order = await session.get(Order, order_id)
        order.proposal_status = "approved"
        order.negotiation_status = "awaiting_payment"
        order.negotiation_status_changed_at = datetime.now()
        proposal = await session.get(OrderProposal, proposal_id)
        proposal.status = "approved"
        await session.commit()
        result = await Mail.get_message(session, actor=actor, message_id=message.id)
        assert not result.delivery_projection_pending
        assert order.proposal_status == proposal.status == "approved"
        assert order.negotiation_status == "awaiting_payment"
