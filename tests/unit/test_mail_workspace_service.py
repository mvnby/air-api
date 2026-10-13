"""Exact-version approval, private bytes and the durable SMTP send fence."""

import smtplib
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, Order, OutgoingEmail, Storefront, Tenant, TenantMembership
from schemas_mail import MailConfirmPayload, MailDraftCreatePayload, MailDraftUpdatePayload, MailVersionPayload
from services.mail_smtp_service import MailAttachment, MailSmtpService
from services.mail_workspace_service import MailWorkspaceService as Mail
from services.mail_workspace_access import MailNotFoundError, MailStateConflictError, MailVersionConflictError

from mail_workspace_test_support import smtp_settings, _actor, _ready, mail_db_engine, mail_db

@pytest.mark.asyncio
async def test_incomplete_draft_persists_without_order_customer_or_transport(mail_db):
    actor = await _actor(mail_db)
    created = await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(), idempotency_key="mail-incomplete-create-001")
    replay = await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(), idempotency_key="mail-incomplete-create-001")
    assert created.value.status == "draft"
    assert created.value.to == []
    assert created.value.order_id is created.value.customer_id is None
    assert replay.replayed and replay.value.id == created.value.id
    saved = await Mail.get_message(mail_db, actor=replace(actor, channel="chatgpt"), message_id=created.value.id)
    assert saved.model_dump() == created.value.model_dump()
    with pytest.raises(ValueError, match="получател"):
        await Mail.confirm(mail_db, actor=actor, draft_id=saved.id,
            payload=MailConfirmPayload(expected_version=1, content_hash=saved.content_hash), idempotency_key="mail-incomplete-confirm-001")
    deleted = await Mail.delete_draft(mail_db, actor=actor, draft_id=saved.id, payload=MailVersionPayload(expected_version=1), idempotency_key="mail-delete-incomplete-001")
    assert deleted.value.status == "deleted"
    with pytest.raises(MailNotFoundError):
        await Mail.get_message(mail_db, actor=actor, message_id=saved.id)

@pytest.mark.asyncio
async def test_edits_refresh_reused_session_and_invalidate_exact_approval(mail_db_engine):
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
        message = await _ready(setup, actor, "versions")
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as reader:
        cached = await reader.get(OutgoingEmail, message.id)
        async with AsyncSession(mail_db_engine, expire_on_commit=False) as writer:
            updated = await Mail.update_draft(writer, actor=actor, draft_id=message.id,
                payload=MailDraftUpdatePayload(expected_version=message.version, body_text="Актуальный полный текст"),
                idempotency_key="mail-versions-update-001")
        assert cached.version == message.version
        current = await Mail.get_message(reader, actor=actor, message_id=message.id)
        assert current.version == cached.version == message.version + 1
        assert current.confirmed_version is None
        with pytest.raises(MailVersionConflictError):
            await Mail.update_draft(reader, actor=actor, draft_id=message.id,
                payload=MailDraftUpdatePayload(expected_version=message.version, subject="Stale edit"), idempotency_key="mail-versions-stale-001")
        with pytest.raises(MailVersionConflictError):
            await Mail.confirm(reader, actor=actor, draft_id=message.id,
                payload=MailConfirmPayload(expected_version=message.version, content_hash=message.content_hash), idempotency_key="mail-versions-stale-confirm-001")
        with pytest.raises(MailStateConflictError, match="предпросмотр|Предпросмотр"):
            await Mail.confirm(reader, actor=actor, draft_id=message.id,
                payload=MailConfirmPayload(expected_version=current.version, content_hash=message.content_hash), idempotency_key="mail-versions-wrong-hash-001")
        with pytest.raises(MailStateConflictError, match="подтвердите"):
            await Mail.send(reader, actor=actor, draft_id=current.id, payload=MailVersionPayload(expected_version=current.version), idempotency_key="mail-versions-unapproved-001")
        with pytest.raises(PermissionError, match="Manager"):
            await Mail.confirm(reader, actor=replace(actor, channel="chatgpt"), draft_id=current.id,
                payload=MailConfirmPayload(expected_version=current.version, content_hash=current.content_hash), idempotency_key="mail-agent-confirm-001")

@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_failure_snapshots_and_safe_recovery(mail_db_engine, monkeypatch, unknown):
    attempts = []
    def transport(message):
        attempts.append(message)
        if unknown:
            raise ConnectionError("Connection lost after DATA")
        raise smtplib.SMTPRecipientsRefused({"supplier@example.test": (550, b"Rejected")})
    monkeypatch.setattr(MailSmtpService, "send_message", staticmethod(transport))
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as mail_db:
        actor = await _actor(mail_db)
        message = await _ready(mail_db, actor, "unknown" if unknown else "failed")
        result = await Mail.send(mail_db, actor=actor, draft_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-first-failure-001")
        assert result.value.status == ("unknown" if unknown else "failed")
        same_message = await Mail.send(mail_db, actor=actor, draft_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-second-failure-001")
        assert same_message.value.status == result.value.status and len(attempts) == 1
        stored = await Mail.get_attachment(mail_db, actor=actor, draft_id=message.id, attachment_id=result.value.attachments[0].id)
        assert stored.content == b"%PDF-1.4 fixed attachment"
        if unknown:
            with pytest.raises(MailStateConflictError, match="проверьте"):
                await Mail.copy_message(mail_db, actor=actor, message_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-unsafe-copy-001")
        else:
            copied = await Mail.copy_message(mail_db, actor=actor, message_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-safe-copy-001")
            assert copied.value.id != message.id and copied.value.status == "draft"
            assert copied.value.attachments[0].sha256 == message.attachments[0].sha256
            assert copied.value.confirmed_version is None
            monkeypatch.setattr(MailSmtpService, "send_message", staticmethod(attempts.append))
            copied = (await Mail.confirm(mail_db, actor=actor, draft_id=copied.value.id,
                payload=MailConfirmPayload(expected_version=copied.value.version, content_hash=copied.value.content_hash), idempotency_key="mail-safe-copy-confirm-001")).value
            second = await Mail.send(mail_db, actor=actor, draft_id=copied.id, payload=MailVersionPayload(expected_version=copied.version), idempotency_key="mail-safe-copy-send-001")
            assert second.value.status == "sent" and len(attempts) == 2
            assert list(attempts[1].iter_attachments())[0].get_payload(decode=True) == stored.content

@pytest.mark.asyncio
async def test_interrupted_claim_becomes_unknown_without_transport(mail_db_engine):
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as mail_db:
        actor = await _actor(mail_db)
        message = await _ready(mail_db, actor, "crash")
        row = await mail_db.get(OutgoingEmail, message.id)
        row.status, row.send_started_at, row.send_token = "sending", datetime.now() - timedelta(minutes=11), "interrupted-token"
        await mail_db.commit()
        recovered = await Mail.get_message(mail_db, actor=actor, message_id=message.id)
        assert recovered.status == "unknown"
        assert (await mail_db.get(OutgoingEmail, message.id)).status == "unknown"
        retry = await Mail.send(mail_db, actor=actor, draft_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-crash-retry-001")
        assert retry.value.status == "unknown"

@pytest.mark.asyncio
async def test_partner_isolation_accounts_links_files_and_revoked_membership(mail_db):
    owner = await _actor(mail_db)
    message = await _ready(mail_db, owner, "isolation")
    partner = Tenant(slug="mail-partner", display_name="Partner", is_system=False)
    mail_db.add(partner)
    await mail_db.flush()
    storefront = Storefront(tenant_id=partner.id, slug="main", display_name="Partner", status="active")
    mail_db.add(storefront)
    await mail_db.flush()
    foreign_customer = Customer(tenant_id=partner.id, name="Private customer", phone="+375291234567")
    mail_db.add(foreign_customer)
    await mail_db.commit()
    outsider = await _actor(mail_db, username="mail-partner", tenant_id=partner.id, storefront_id=storefront.id, is_system=False)
    assert (await Mail.get_accounts(mail_db, actor=outsider)).items == []
    assert (await Mail.list_messages(mail_db, actor=outsider, folder="outbox")).items == []
    with pytest.raises(MailNotFoundError):
        await Mail.get_message(mail_db, actor=outsider, message_id=message.id)
    with pytest.raises(MailNotFoundError):
        await Mail.get_attachment(mail_db, actor=outsider, draft_id=message.id, attachment_id=message.attachments[0].id)
    with pytest.raises(PermissionError):
        await Mail.create_draft(mail_db, actor=outsider, payload=MailDraftCreatePayload(), idempotency_key="mail-partner-create-001")
    with pytest.raises(MailNotFoundError):
        await Mail.create_draft(mail_db, actor=owner, payload=MailDraftCreatePayload(customer_id=foreign_customer.id), idempotency_key="mail-foreign-link-001")
    membership = (await mail_db.execute(select(TenantMembership).where(TenantMembership.staff_user_id == owner.staff_user_id))).scalar_one()
    membership.status = "suspended"
    await mail_db.commit()
    with pytest.raises(PermissionError):
        await Mail.get_message(mail_db, actor=owner, message_id=message.id)
    with pytest.raises(PermissionError):
        await Mail.confirm(mail_db, actor=owner, draft_id=message.id, payload=MailConfirmPayload(expected_version=message.version, content_hash=message.content_hash), idempotency_key="mail-revoked-confirm-001")

@pytest.mark.asyncio
async def test_attachment_replay_does_not_fetch_rotating_download_again(mail_db):
    actor = await _actor(mail_db)
    message = (await Mail.create_draft(mail_db, actor=actor, payload=MailDraftCreatePayload(), idempotency_key="mail-loader-draft-001")).value
    calls = []
    async def loader():
        calls.append(1)
        return b"fixed uploaded file"
    kwargs = dict(actor=actor, draft_id=message.id, expected_version=1, idempotency_key="mail-loader-file-001",
        filename="details.txt", mime_type="text/plain", source_file_id="chatgpt-file-123", loader=loader)
    first = await Mail.upload_attachment(mail_db, **kwargs)
    replay = await Mail.upload_attachment(mail_db, **kwargs)
    assert first.value.version == 2 and replay.replayed and len(calls) == 1
    assert first.value.attachments[0].sha256 == replay.value.attachments[0].sha256

@pytest.mark.asyncio
async def test_legacy_order_draft_preserves_private_documents_and_html_becomes_reviewable_text(mail_db):
    actor = await _actor(mail_db)
    order = Order(tenant_id=1, storefront_id=1, title="Existing order")
    mail_db.add(order)
    await mail_db.commit()
    created = await Mail.create_legacy_draft(mail_db, actor=actor, idempotency_key="mail-legacy-order-draft-001",
        to_email="client@example.test", subject="Documents", body_html="<p>Полный согласуемый текст</p><script>hidden()</script>",
        order_id=order.id, attachments=[MailAttachment(filename="invoice.pdf", content=b"fixed document", mime_type="application/pdf", metadata={"document_id": 123})])
    assert created.value.order_id == order.id and created.value.body_text == "Полный согласуемый текст"
    row = await mail_db.get(OutgoingEmail, created.value.id)
    assert row.body_html is None
    assert row.attachments[0]["document_id"] == 123
    assert (await Mail.list_messages(mail_db, actor=actor, folder="drafts", order_id=order.id)).total == 1


@pytest.mark.asyncio
async def test_send_rejects_uncommitted_external_transaction(mail_db_engine):
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
        message = await _ready(setup, actor, "outer-transaction")
    async with mail_db_engine.connect() as connection:
        async with connection.begin():
            async with AsyncSession(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                with pytest.raises(ValueError, match="транзакции"):
                    await Mail.send(db, actor=actor, draft_id=message.id, payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-uncommitted-001")


@pytest.mark.asyncio
async def test_revoked_connector_after_claim_is_known_not_sent(mail_db_engine):
    from services.connector_auth_policy import ConnectorAuthError
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as db:
        actor = await _actor(db)
        message = await _ready(db, actor, "revoked-connector")
        async def deny():
            raise ConnectorAuthError("invalid_token", "Grant revoked", 401)
        with pytest.raises(ConnectorAuthError, match="revoked"):
            await Mail.send(db, actor=replace(actor, channel="chatgpt"), draft_id=message.id,
                payload=MailVersionPayload(expected_version=message.version), idempotency_key="mail-send-revoked-grant-001", authorize_before_send=deny)
        current = await Mail.get_message(db, actor=actor, message_id=message.id)
        assert current.status == "failed" and current.sent_at is None
        assert current.message_id is not None


@pytest.mark.asyncio
async def test_manager_confirmation_requires_credential_bound_csrf(mail_db_engine):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from core.database import get_session
    from core.security import AuthenticatedUser, get_current_auth_context
    from routers.manager_mail_workspace import router
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup)
        message = (await Mail.create_draft(setup, actor=actor, payload=MailDraftCreatePayload(
            to=["supplier@example.test"], subject="Approval", body_text="Full text"), idempotency_key="mail-api-create-001")).value
    app = FastAPI()
    app.include_router(router)
    async def session():
        async with AsyncSession(mail_db_engine, expire_on_commit=False) as db:
            yield db
    async def auth():
        return AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id,
            role="manager", tenant_id=1, storefront_id=1, is_system_tenant=True)
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_auth_context] = auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={"access_token": "this-manager-session"}) as client:
        preview = await client.get(f"/api/manager/mail/drafts/{message.id}/preview")
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "no-store"
        reviewed = preview.json()
        body = {"expected_version": message.version, "content_hash": reviewed["content_hash"]}
        url = f"/api/manager/mail/drafts/{message.id}/confirm"
        basic = {"Idempotency-Key": "mail-api-confirm-001", "X-Kitlane-Mail-Approval": "manager-review"}
        missing = await client.post(url, json=body, headers=basic)
        assert missing.status_code == 403
        forged = await client.post(url, json=body, headers={**basic, "X-CSRF-Token": "agent-set-true"})
        assert forged.status_code == 403
        confirmed = await client.post(url, json=body, headers={**basic, "X-CSRF-Token": reviewed["csrf_token"]})
        assert confirmed.status_code == 200 and confirmed.json()["confirmed_version"] == message.version
        assert confirmed.json()["status"] == "draft"
        # A token read with another authenticated session is not transferable.
        client.cookies.set("access_token", "another-manager-session")
        wrong_session = await client.post(url, json=body, headers={**basic, "X-CSRF-Token": reviewed["csrf_token"]})
        assert wrong_session.status_code == 403


@pytest.mark.asyncio
async def test_replayed_receipt_requires_access_to_current_link(mail_db):
    actor = await _actor(mail_db)
    payload = MailDraftCreatePayload(subject="Saved receipt")
    created = await Mail.create_draft(mail_db, actor=actor, payload=payload, idempotency_key="mail-access-replay-create-001")
    other_storefront = Storefront(tenant_id=1, slug="other-store", display_name="Other", status="active")
    mail_db.add(other_storefront)
    await mail_db.flush()
    foreign_order = Order(tenant_id=1, storefront_id=other_storefront.id, title="Other context")
    mail_db.add(foreign_order)
    await mail_db.flush()
    row = await mail_db.get(OutgoingEmail, created.value.id)
    row.order_id = foreign_order.id
    await mail_db.commit()
    with pytest.raises(MailNotFoundError, match="заказ"):
        await Mail.create_draft(mail_db, actor=actor, payload=payload, idempotency_key="mail-access-replay-create-001")
