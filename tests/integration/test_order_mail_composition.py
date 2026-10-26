"""The 590-shaped path fixes context and identity before any real transport."""
import pytest

from mail_workspace_test_support import _actor, smtp_settings
from models import Order, OrderDocument, OrderProposal, OrderServiceLink
from schemas_order_mail import MailOrderDraftPayload
from services.mail_workspace_service import MailWorkspaceService
from services.order_mail_delivery_service import OrderMailDeliveryService


@pytest.mark.asyncio
async def test_order_draft_keeps_document_scope_signature_and_original_bytes(db, monkeypatch):
    actor = await _actor(db, username="vadim-proposal-mail")
    from models import StaffUser
    person = await db.get(StaffUser, actor.staff_user_id)
    person.display_name = "Вадим"
    order = Order(tenant_id=1, storefront_id=1, title="Обслуживание", workflow_type="service_work", status="negotiation")
    db.add(order)
    await db.flush()
    selected = OrderProposal(order_id=order.id, name="Основное", status="sent", is_selected=True)
    alternative = OrderProposal(order_id=order.id, name="Чужой ремонт", status="draft", is_selected=False)
    db.add_all([selected, alternative])
    await db.flush()
    db.add(OrderServiceLink(order_id=order.id, proposal_id=alternative.id, title="Ремонт", quantity=1, price=900))
    document = OrderDocument(order_id=order.id, proposal_id=selected.id, doc_type="offer", number="КП-2026-024",
        snapshot_version=1, render_snapshot={"meta": {"proposal_id": selected.id}, "table_rows": {"lines": [
            {"line.kind": "service", "line.title": "Стандартный монтаж настенного кондиционера свыше 4,2 и менее 8 кВт", "line.quantity": "2", "line.unit_price": "810", "line.amount": "1620"}]}})
    db.add(document)
    await db.commit()
    async def download(*args, **kwargs):
        return b"%PDF original approved installation", "KP-2026-024.pdf"
    monkeypatch.setattr("services.mail_smtp_service.DocumentService.get_download_stream", download)
    payload = MailOrderDraftPayload(template_key="auto", to_email="customer@example.test", document_ids=[document.id])
    created = await OrderMailDeliveryService.create_draft(db, actor=actor, order_id=order.id, payload=payload, idempotency_key="proposal-mail-590-create")
    draft = created.value
    assert draft.subject == "Коммерческое предложение на монтаж оборудования"
    assert "ремонт" not in draft.body_text.lower() and "обслуживание" not in draft.body_text.lower()
    assert "С уважением,\nВадим\nМастер Воздуха" in draft.body_text
    assert draft.attachments[0].filename == "KP-2026-024.pdf"
    document.render_snapshot = {"table_rows": {"lines": [{"line.kind": "service", "line.title": "Обслуживание"}]}}
    document.snapshot_version = 2
    person.display_name = "Изменённое имя"
    await db.commit()
    repeated = await OrderMailDeliveryService.create_draft(db, actor=actor, order_id=order.id, payload=payload, idempotency_key="proposal-mail-590-create")
    assert repeated.replayed and repeated.value.id == draft.id
    reopened = await MailWorkspaceService.get_message(db, actor=actor, message_id=draft.id)
    assert reopened.body_text == draft.body_text
    stored = await MailWorkspaceService.get_attachment(db, actor=actor, draft_id=draft.id, attachment_id=draft.attachments[0].id)
    assert stored.content == b"%PDF original approved installation"
    assert stored.source_metadata["mail_scenario"] == "монтаж оборудования"
    assert stored.source_metadata["snapshot_version"] == 1
