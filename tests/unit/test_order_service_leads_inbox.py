from datetime import datetime, timedelta

import pytest

from models import Customer, CustomerType, LeadSource, Order, OrderStatus
from schemas import ManagerOrderUpdatePayload
from services.order_service import OrderService

from models.tenancy import TenantScope

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


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

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=2, tenant_scope=TEST_TENANT_SCOPE)

    assert response.total == 3
    assert response.meta.total == 3
    assert response.meta.page == 1
    assert response.meta.limit == 2
    assert response.meta.pages == 2
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

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

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

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert response.items[0].source_created_at == datetime(2026, 5, 11, 12, 33)


@pytest.mark.asyncio
async def test_leads_inbox_ignores_invalid_no_answer_at(db):
    customer = Customer(name="Bad Date Lead", phone="+375292222223", email="bad-date@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.MANAGER,
            technical_meta={"no_answer_at": "not-a-date"},
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert response.items[0].no_answer_at is None


@pytest.mark.asyncio
async def test_leads_inbox_keeps_unknown_customer_type_and_task_essence_null(db):
    customer = Customer(name="Default Individual", phone="+375290000001", type=CustomerType.individual)
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.MANAGER,
            comment="Нужно уточнить, кто клиент и что именно требуется.",
            technical_meta={},
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert response.items[0].customer_id == customer.id
    assert response.items[0].customer_type is None
    assert response.items[0].service_type is None


@pytest.mark.asyncio
async def test_leads_inbox_returns_known_type_and_task_when_stored(db):
    customer = Customer(
        name="ООО Климат",
        phone="+375293333333",
        type=CustomerType.company,
        inn="123456789",
    )
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.MANAGER,
            delivery_address="Минск, объект 1",
            technical_meta={
                "service_type": "maintenance",
                "object_type": "office",
                "equipment_class": "standard",
                "marketing_source": "referral",
            },
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)
    item = response.items[0]

    assert item.customer_type == "company"
    assert item.service_type == "maintenance"
    assert item.customer_delivery_address == "Минск, объект 1"
    assert item.object_type == "office"
    assert item.equipment_class == "standard"
    assert item.marketing_source == "referral"


@pytest.mark.asyncio
async def test_leads_inbox_returns_confirmed_individual_customer_type(db):
    customer = Customer(name="Иван", phone="+375294444444", type=CustomerType.individual)
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.MANAGER,
            technical_meta={
                "lead_customer_type_known": True,
                "lead_customer_type": "individual",
            },
        )
    )
    await db.commit()

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert response.items[0].customer_type == "individual"


@pytest.mark.asyncio
async def test_linking_existing_individual_marks_lead_customer_type_known(db):
    default_customer = Customer(name="Новый клиент", phone="", type=CustomerType.individual)
    existing_customer = Customer(name="Постоянный клиент", phone="+375295555555", type=CustomerType.individual)
    db.add(default_customer)
    db.add(existing_customer)
    await db.flush()
    order = Order(
        customer_id=default_customer.id,
        status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.MANAGER,
        technical_meta={},
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    await OrderService.update_order_for_manager(
        db,
        int(order.id),
        ManagerOrderUpdatePayload(customer_id=int(existing_customer.id)),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    response = await OrderService.get_leads_inbox(db, scope="active", page=1, limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert response.items[0].customer_id == existing_customer.id
    assert response.items[0].customer_type == "individual"
