"""PostgreSQL evidence for read-only original projection and scope boundaries."""
from dataclasses import replace

import pytest
from sqlalchemy import select

from models import Order, ServiceAttachment, OrderAttachmentLink, TenantMembership
from models.incoming_mail import IncomingMail, IncomingMailAttachment
from models.tenancy import TenantScope
from mail_workspace_test_support import _actor
from services.order_request_context_service import OrderRequestContextService as Context
from services.incoming_mail_service import IncomingMailService


async def seed(db, *, source="email"):
    actor = await _actor(db)
    order = Order(tenant_id=1, storefront_id=1, title="Synthetic request", lead_source=source,
        comment="Edited working description", technical_meta={"email_source_message_id": "<source@test.invalid>"})
    db.add(order)
    await db.flush()
    return actor, order


@pytest.mark.asyncio
async def test_saved_mail_and_private_links_dedupe_by_bytes_preserving_missing_files_and_comment(db):
    actor, order = await seed(db)
    attachment = ServiceAttachment(original_filename="private.pdf", mime_type="application/pdf", size_bytes=4,
        content_hash="a" * 64, storage_key="private/original", source="email_lead_intake")
    db.add(attachment)
    await db.flush()
    db.add(OrderAttachmentLink(order_id=order.id, attachment_id=attachment.id))
    message = IncomingMail(tenant_id=1, source_key="source", message_id="<source@test.invalid>",
        body_text="Original customer wording", subject="Request", attachments=[
            {"id": 143, "filename": "mail-copy.pdf", "mime_type": "application/pdf", "size": 4, "sha256": "a" * 64, "available": True},
            {"id": 144, "filename": "second.pdf", "mime_type": "application/pdf", "size": 5, "sha256": "b" * 64, "available": True},
            {"id": None, "filename": "missing.pdf", "size": 9, "sha256": "c" * 64, "available": False},
        ])
    db.add(message)
    await db.flush()
    # Same filename with different bytes must remain a distinct original.
    db.add(IncomingMail(tenant_id=1, source_key="followup", order_id=order.id, attachments=[
        {"id": 145, "filename": "second.pdf", "size": 6, "sha256": "d" * 64, "available": True}]))
    db.add(IncomingMail(tenant_id=1, source_key="unrelated", body_text="Must not appear", attachments=[
        {"id": 146, "filename": "unrelated.pdf", "available": True}]))
    await db.flush()
    first = await Context.read(db, order_id=order.id, actor=actor)
    second = await Context.read(db, order_id=order.id, actor=actor)
    assert first == second
    assert [file.filename for file in first.files] == ["private.pdf", "second.pdf", "missing.pdf", "second.pdf"]
    assert first.files[1].id == -144 and first.files[1].mail_message_id == -message.id
    assert first.files[2].available is False
    assert first.sources[0].text == "Original customer wording"
    assert order.comment == "Edited working description"
    assert list((await db.execute(select(IncomingMailAttachment))).scalars()) == []  # no copy-on-read
    assert len(list((await db.execute(select(OrderAttachmentLink))).scalars())) == 1


@pytest.mark.asyncio
async def test_available_mail_original_replaces_known_unavailable_private_copy(db):
    actor, order = await seed(db)
    attachment = ServiceAttachment(original_filename="unavailable.pdf", content_hash="a" * 64)
    db.add(attachment)
    await db.flush()
    db.add(OrderAttachmentLink(order_id=order.id, attachment_id=attachment.id))
    db.add(IncomingMail(tenant_id=1, source_key="source", order_id=order.id, attachments=[
        {"id": 143, "filename": "available.pdf", "size": 4, "sha256": "a" * 64, "available": True}]))
    await db.flush()
    result = await Context.read(db, order_id=order.id, actor=actor)
    assert len(result.files) == 1 and result.files[0].available and result.files[0].id == -143


@pytest.mark.asyncio
async def test_foreign_storefront_and_tenant_return_nothing_and_revoked_mail_membership_denied(db):
    actor, order = await seed(db)
    for scope in [TenantScope(2, 2, is_system=False), TenantScope(1, 2, is_system=True)]:
        assert await Context.read(db, order_id=order.id, actor=replace(actor, tenant_scope=scope)) is None
    membership = (await db.execute(select(TenantMembership).where(TenantMembership.staff_user_id == actor.staff_user_id))).scalar_one()
    membership.status = "suspended"
    await db.flush()
    with pytest.raises(PermissionError):
        await Context.read(db, order_id=order.id, actor=actor)


@pytest.mark.asyncio
async def test_manual_empty_does_not_query_mail_and_fallback_never_uses_working_comment(db, monkeypatch):
    actor, order = await seed(db, source="manager")
    async def no_mail(*args, **kwargs):
        pytest.fail("Manual request must not read system mail")
    monkeypatch.setattr(IncomingMailService, "_require_access", no_mail)
    result = await Context.read(db, order_id=order.id, actor=actor)
    assert result.sources == result.files == result.warnings == []
    order.lead_source = "email"
    monkeypatch.undo()
    order.technical_meta = {"email_source_text": "Original excerpt", "email_source_text_truncated": True}
    await db.flush()
    result = await Context.read(db, order_id=order.id, actor=actor)
    assert result.sources[0].text == "Original excerpt" and result.sources[0].truncated
    assert order.comment not in [source.text for source in result.sources]


@pytest.mark.asyncio
async def test_tender_uses_existing_reviewed_card_and_saved_originals(db):
    actor, order = await seed(db, source="belzakupki")
    order.technical_meta = {"belzakupki": {"source": "belzakupki", "external_tender_id": "123", "tender": {
        "title": "Synthetic tender", "source_url": "https://example.test/tender/123"},
        "enrichment": {"source": "belzakupki", "external_id": "123", "work_summary": "Replace equipment"}}}
    await db.flush()
    result = await Context.read(db, order_id=order.id, actor=actor)
    assert result.sources[0].label == "Проработанная заявка тендера"
    assert "Replace equipment" in result.sources[0].text
    assert result.sources[0].url == "https://example.test/tender/123"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["installer", "catalog_editor"])
async def test_route_rejects_non_manager_before_loading_evidence(async_client, monkeypatch, role):
    from core.security import AuthenticatedUser, get_current_auth_context
    from main import app
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(
        username="reader", auth_source="jwt", staff_user_id=1, role=role,
        tenant_id=1, storefront_id=1, is_system_tenant=True)
    async def unexpected(*args, **kwargs):
        pytest.fail("Non-manager must not read request evidence")
    monkeypatch.setattr(Context, "read", unexpected)
    try:
        response = await async_client.get("/api/manager/orders/590/request-context")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_auth_context, None)
