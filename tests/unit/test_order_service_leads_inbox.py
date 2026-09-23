from datetime import datetime, timedelta, timezone

import pytest

from models import Customer, CustomerType, LeadSource, Order, OrderStatus
from schemas import ManagerOrderUpdatePayload
from services.order_service import OrderService

from models.tenancy import TenantScope
from models.tenancy import Storefront, Tenant

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_leads_inbox_is_paginated(db):
    now = datetime.now()
    for idx in range(3):
        customer = Customer(tenant_id=1, name=f"Lead {idx}", phone=f"+37529000000{idx}")
        db.add(customer)
        await db.flush()
        db.add(
            Order(
                tenant_id=1,
                storefront_id=1,
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
async def test_leads_inbox_search_and_source_filter_before_pagination_with_tenant_scope(db):
    foreign_tenant = Tenant(slug="foreign-inbox", display_name="Foreign")
    db.add(foreign_tenant)
    await db.flush()
    foreign_storefront = Storefront(tenant_id=foreign_tenant.id, slug="main", display_name="Foreign")
    db.add(foreign_storefront)
    await db.flush()

    when = datetime(2026, 9, 1, 10)
    for idx in range(6):
        customer = Customer(
            tenant_id=1,
            name=f"Customer {idx}",
            email="deep@example.test" if idx == 0 else None,
        )
        db.add(customer)
        await db.flush()
        db.add(Order(
            tenant_id=1, storefront_id=1, customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.EMAIL if idx < 3 else LeadSource.SITE,
            comment="special tender" if idx == 1 else None,
            created_at=when,
        ))
    foreign_customer = Customer(tenant_id=foreign_tenant.id, name="Foreign special tender")
    db.add(foreign_customer)
    await db.flush()
    db.add(Order(
        tenant_id=foreign_tenant.id, storefront_id=foreign_storefront.id,
        customer_id=foreign_customer.id, status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.EMAIL, comment="special tender", created_at=when,
    ))
    await db.commit()

    first = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, page=1, limit=2)
    second = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, page=2, limit=2)
    assert first.total == second.total == 6
    assert [item.id for item in first.items] == sorted([item.id for item in first.items], reverse=True)
    assert set(item.id for item in first.items).isdisjoint(item.id for item in second.items)

    email = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, page=2, limit=2, source=LeadSource.EMAIL)
    assert email.total == email.meta.total == 3
    assert len(email.items) == 1
    deep = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, page=1, limit=2, search="deep@example.test")
    assert deep.total == 1
    assert deep.items[0].email == "deep@example.test"
    combined = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, page=1, limit=2, search="special tender", source=LeadSource.EMAIL)
    assert combined.total == 1
    assert combined.items[0].comment == "special tender"
    no_foreign = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE, search="Foreign special tender")
    assert no_foreign.total == 0


@pytest.mark.asyncio
async def test_leads_inbox_exposes_tender_context_without_changing_comment(db):
    order = Order(
        tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.BELZAKUPKI, comment="Менеджерский комментарий",
        technical_meta={"belzakupki": {
            "tender": {"source": "goszakupki", "url": "https://example.test/tender/1", "deadline_at": "2026-10-01T10:00:00+00:00", "customer_name": "Заказчик"},
            "matches": {"42": {"reason": "Подходит профиль", "profile": {"name": "Вентиляция"}}},
        }},
    )
    db.add(order)
    await db.commit()
    response = await OrderService.get_leads_inbox(db, tenant_scope=TEST_TENANT_SCOPE)
    item = response.items[0]
    assert item.customer_name == "Заказчик"
    assert item.comment == "Менеджерский комментарий"
    assert item.tender.source == "goszakupki"
    assert item.tender.url == "https://example.test/tender/1"
    assert item.tender.deadline_at == datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    assert item.tender.reason == "Подходит профиль"
    assert item.tender.profile_name == "Вентиляция"


@pytest.mark.asyncio
async def test_leads_inbox_uses_email_date_for_email_source(db):
    customer = Customer(tenant_id=1, name="Email Lead", phone="+375291111111", email="client@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
    customer = Customer(tenant_id=1, name="Legacy Email Lead", phone="+375292222222", email="legacy@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
    customer = Customer(tenant_id=1, name="Bad Date Lead", phone="+375292222223", email="bad-date@example.com")
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
    customer = Customer(tenant_id=1, name="Default Individual", phone="+375290000001", type=CustomerType.individual)
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
        tenant_id=1,
        name="ООО Климат",
        phone="+375293333333",
        type=CustomerType.company,
        inn="123456789",
    )
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
    customer = Customer(tenant_id=1, name="Иван", phone="+375294444444", type=CustomerType.individual)
    db.add(customer)
    await db.flush()
    db.add(
        Order(
            tenant_id=1,
            storefront_id=1,
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
    default_customer = Customer(tenant_id=1, name="Новый клиент", phone="", type=CustomerType.individual)
    existing_customer = Customer(tenant_id=1, name="Постоянный клиент", phone="+375295555555", type=CustomerType.individual)
    db.add(default_customer)
    db.add(existing_customer)
    await db.flush()
    order = Order(
        tenant_id=1,
        storefront_id=1,
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
