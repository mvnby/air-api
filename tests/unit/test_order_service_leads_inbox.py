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


@pytest.mark.asyncio
async def test_leads_inbox_uses_email_date_for_email_source(db):
    customer = Customer(name="Email Lead", phone="+375291111111", email="client@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.EMAIL,
            created_at=datetime(2026, 5, 27, 21, 40),
            technical_meta={"email_date": "2026-05-13T16:59"},
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10)

    assert response.items[0].email == "client@example.com"
    assert response.items[0].created_at == datetime(2026, 5, 27, 21, 40)
    assert response.items[0].source_created_at == datetime(2026, 5, 13, 16, 59)


@pytest.mark.asyncio
async def test_leads_inbox_extracts_legacy_email_date_from_comment(db):
    customer = Customer(name="Legacy Email Lead", phone="+375292222222", email="legacy@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.EMAIL,
            created_at=datetime(2026, 5, 27, 21, 40),
            comment="Просьба подготовить предложение.\n\nДата письма: 2026-05-11T12:33\n\nТема письма: Заявка",
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10)

    assert response.items[0].source_created_at == datetime(2026, 5, 11, 12, 33)
