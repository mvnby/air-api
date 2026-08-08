from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models import IntegrationOutboxEvent
from services.communications.contracts import (
    PublicOrderCustomerSnapshotV1,
    TenantWebsiteCheckoutCreatedPayloadV1,
)
from services.communications.installation_notifications import (
    InstallationNotificationOperations,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
)
from tests.unit.test_communications_dispatcher import (
    communications_session_factory,
)


@pytest.mark.asyncio
async def test_activation_inventory_includes_new_tenant_website_events(
    communications_session_factory,
):
    now = datetime.now(timezone.utc)
    payload = TenantWebsiteCheckoutCreatedPayloadV1(
        tenant_id=1,
        storefront_id=1,
        order_id=77,
        status="negotiation",
        customer=PublicOrderCustomerSnapshotV1(
            name="Checkout",
            phone="+375291112233",
        ),
        total_amount=100,
    )
    async with communications_session_factory() as session:
        session.add(
            IntegrationOutboxEvent(
                event_id="7" * 32,
                event_type=TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
                schema_version=1,
                aggregate_type="order",
                aggregate_id="77",
                deduplication_key="tenant-website-activation-scope:77",
                payload=payload.model_dump(mode="json"),
                status="pending",
                available_at=now,
                occurred_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

        backlog = await InstallationNotificationOperations._backlog_count(
            session,
            cutoff=None,
        )
        outbox_counts, _, _, _ = (
            await InstallationNotificationOperations._status_counts(session)
        )

    assert backlog == 1
    assert outbox_counts["pending"] == 1
