"""Link a follow-up email without losing its source or duplicating attachments."""

import pytest
from sqlmodel import select

from models import LeadSource, Order, OrderAttachmentLink, OrderStatus, ServiceAttachment
from models.tenancy import TenantScope
from services.email_lead_order_link_service import EmailLeadOrderLinkService
from services.order_service import OrderService


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_link_moves_email_out_of_active_inbox_and_can_be_relinked(db):
    source = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source=LeadSource.EMAIL)
    target = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add_all([source, target])
    await db.flush()
    file = ServiceAttachment(original_filename="contract.doc", mime_type="application/msword", source="email_lead_intake")
    db.add(file)
    await db.flush()
    db.add(OrderAttachmentLink(order_id=source.id, attachment_id=file.id, category="document"))
    await db.commit()

    first = await EmailLeadOrderLinkService.link(
        db, source_order_id=source.id, target_order_id=target.id,
        linked_by="manager", tenant_scope=SCOPE,
    )
    assert first["linked_files"] == 1
    active = await OrderService.get_leads_inbox(db, scope="active", tenant_scope=SCOPE)
    archived = await OrderService.get_leads_inbox(db, scope="archive", tenant_scope=SCOPE)
    assert source.id not in {item.id for item in active.items}
    assert archived.items[0].linked_order_id == target.id

    assert await EmailLeadOrderLinkService.unlink(db, source_order_id=source.id, tenant_scope=SCOPE) == target.id
    second = await EmailLeadOrderLinkService.link(
        db, source_order_id=source.id, target_order_id=target.id,
        linked_by="manager", tenant_scope=SCOPE,
    )
    assert second["linked_files"] == 1
    mirrors = (await db.execute(select(OrderAttachmentLink).where(
        OrderAttachmentLink.order_id == target.id,
        OrderAttachmentLink.origin_order_id == source.id,
    ))).scalars().all()
    assert len(mirrors) == 1
    assert mirrors[0].archived_at is None
