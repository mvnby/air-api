from datetime import datetime, timedelta

import pytest

from models import Customer, LeadSource, Order, OrderStatus
from services.order_service import OrderService


@pytest.mark.asyncio
async def test_leads_inbox_is_paginated(db):
    now = datetime.now()
    for idx in range(3):
        customer = Customer(name=f"Lead {idx}", phone=f"+37529000000{idx}")
        db.add(customer)
        await db.flush()
        db.add(
            Order(
                customer_id=customer.id,
                status=OrderStatus.NEW_LEAD,
                lead_source=LeadSource.MANAGER,
                created_at=now + timedelta(minutes=idx),
            )
        )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=2)

    assert response.total == 3
    assert len(response.items) == 2
    assert [item.customer_name for item in response.items] == ["Lead 2", "Lead 1"]
