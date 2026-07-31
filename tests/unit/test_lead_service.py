from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from models import Customer, CustomerBranch, CustomerType, Lead, Order
from schemas import LeadCreatePayload, LeadLossPayload, LeadQualifyPayload, LeadUpdatePayload
from services.lead_service import LeadService
from services.tenant_scope_service import TenantScope

from models.tenancy import TenantScope

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_create_lead_with_inn_sets_b2b(db, tenant_scope):
    payload = LeadCreatePayload(
        source="phone",
        name="ООО Тест",
        inn="123456789",
        request_text="Нужен компрессор",
    )

    lead_data = await LeadService.create_lead(db, payload, tenant_scope=tenant_scope)
    lead = await db.get(Lead, lead_data["id"])

    assert lead_data["segment_hint"] == "b2b"
    assert lead is not None
    assert lead.tenant_id == tenant_scope.tenant_id
    assert lead.storefront_id == tenant_scope.storefront_id


@pytest.mark.asyncio
async def test_create_lead_without_inn_sets_unknown(db, tenant_scope):
    payload = LeadCreatePayload(
        source="phone",
        name="Иван",
        phone="+375291111111",
        request_text="Нужна консультация",
    )

    lead_data = await LeadService.create_lead(db, payload, tenant_scope=tenant_scope)
    lead = await db.get(Lead, lead_data["id"])

    assert lead_data["segment_hint"] == "unknown"
    assert lead is not None
    assert lead.tenant_id == tenant_scope.tenant_id
    assert lead.storefront_id == tenant_scope.storefront_id


@pytest.mark.asyncio
async def test_qualify_lead_reuses_customer_by_phone(db, tenant_scope):
    customer = Customer(name="Existing", phone="+375292222222", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Existing Updated",
            phone="+375292222222",
            request_text="Нужен кондиционер",
        ),
        tenant_scope=tenant_scope,
    )

    result = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(order_comment="Проверить наличие"),
        tenant_scope=tenant_scope,
    )

    assert result is not None
    assert result["customer_id"] == customer.id
    assert result["order_id"] > 0

    refreshed_customer = await db.get(Customer, customer.id)
    assert refreshed_customer is not None
    assert refreshed_customer.name == "Existing Updated"


@pytest.mark.asyncio
async def test_qualify_lead_creates_order_and_updates_status(db, tenant_scope):
    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="email",
            name="Пётр",
            email="petr@example.com",
            request_text="Ищу сервис",
        ),
        tenant_scope=tenant_scope,
    )

    result = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(
            phone="+375293333333",
            delivery_address="Минск, ул. Примерная 1",
            order_comment="Квалифицированный лид",
        ),
        tenant_scope=tenant_scope,
    )

    assert result is not None
    assert result["lead"]["status"] == "qualified"
    assert result["lead"]["converted_order_id"] == result["order_id"]

    order = await db.get(Order, result["order_id"])
    lead = await db.get(Lead, lead_data["id"])
    assert order is not None
    assert lead is not None
    assert order.customer_id == result["customer_id"]
    assert order.lead_source == "email"
    assert order.comment == "Квалифицированный лид"
    assert order.tenant_id == tenant_scope.tenant_id
    assert order.storefront_id == tenant_scope.storefront_id
    assert lead.tenant_id == order.tenant_id
    assert lead.storefront_id == order.storefront_id


@pytest.mark.asyncio
async def test_qualify_lead_rejects_mismatched_tenant_scope(db, tenant_scope):
    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Wrong tenant scope",
            request_text="Проверка изоляции tenant",
        ),
        tenant_scope=tenant_scope,
    )

    mismatched_scope = TenantScope(
        tenant_id=tenant_scope.tenant_id + 1,
        storefront_id=tenant_scope.storefront_id,
    )
    result = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(order_comment="Не должен создаться"),
        tenant_scope=mismatched_scope,
    )

    assert result is None
    orders = (await db.execute(select(Order))).scalars().all()
    assert orders == []


@pytest.mark.asyncio
async def test_qualify_lead_is_idempotent_after_conversion(db, tenant_scope):
    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="email",
            name="Retry Lead",
            email="retry@example.com",
            request_text="Повторная квалификация",
        ),
        tenant_scope=tenant_scope,
    )

    first = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(order_comment="Первый запуск"),
        tenant_scope=tenant_scope,
    )
    second = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(order_comment="Повторный запуск"),
        tenant_scope=tenant_scope,
    )

    assert first is not None
    assert second is not None
    assert second["order_id"] == first["order_id"]
    orders = (await db.execute(select(Order))).scalars().all()
    assert len(orders) == 1


@pytest.mark.asyncio
async def test_update_lead_rejects_terminal_status_shortcut(db, tenant_scope):
    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Shortcut Lead",
            request_text="Нельзя обходить квалификацию",
        ),
        tenant_scope=tenant_scope,
    )

    with pytest.raises(ValueError, match="dedicated lead workflow"):
        await LeadService.update_lead(
            db,
            lead_id=lead_data["id"],
            payload=LeadUpdatePayload(status="qualified"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    lead = await db.get(Lead, lead_data["id"])
    assert lead is not None
    assert lead.status == "new"
    assert lead.converted_order_id is None


@pytest.mark.asyncio
async def test_mark_lost_rejects_non_loss_status(db, tenant_scope):
    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Bad Lost Status",
            request_text="Нельзя отмечать qualified через mark-lost",
        ),
        tenant_scope=tenant_scope,
    )

    with pytest.raises(ValueError, match="lost or spam"):
        await LeadService.mark_lead_lost(
            db,
            lead_id=lead_data["id"],
            payload=LeadLossPayload(status="qualified"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    lead = await db.get(Lead, lead_data["id"])
    assert lead is not None
    assert lead.status == "new"


@pytest.mark.asyncio
async def test_qualify_lead_with_customer_branch_sets_order_branch_and_snapshot(db, tenant_scope):
    customer = Customer(name="Branch Owner", phone="+375291010101", type=CustomerType.company, inn="111111111")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    branch = CustomerBranch(
        customer_id=customer.id,
        name="Склад Минск",
        delivery_address="Минск, Притыцкого 1",
        is_default=True,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Lead with branch",
            request_text="Нужна поставка на склад",
        ),
        tenant_scope=tenant_scope,
    )

    result = await LeadService.qualify_lead(
        db,
        lead_id=lead_data["id"],
        payload=LeadQualifyPayload(
            customer_id=customer.id,
            customer_branch_id=branch.id,
            order_comment="Сделка с филиалом",
        ),
        tenant_scope=tenant_scope,
    )

    assert result is not None
    order = await db.get(Order, result["order_id"])
    assert order is not None
    assert order.customer_id == customer.id
    assert order.customer_branch_id == branch.id
    assert order.delivery_address == "Минск, Притыцкого 1"


@pytest.mark.asyncio
async def test_qualify_lead_rejects_foreign_customer_branch(db, tenant_scope):
    customer_a = Customer(name="Customer A", phone="+375291111111", type=CustomerType.company, inn="222222222")
    customer_b = Customer(name="Customer B", phone="+375292222222", type=CustomerType.company, inn="333333333")
    db.add(customer_a)
    db.add(customer_b)
    await db.commit()
    await db.refresh(customer_a)
    await db.refresh(customer_b)

    branch_b = CustomerBranch(
        customer_id=customer_b.id,
        name="Branch B",
        delivery_address="Гомель, Советская 2",
        is_default=True,
    )
    db.add(branch_b)
    await db.commit()
    await db.refresh(branch_b)

    lead_data = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="manager",
            name="Lead invalid branch",
            request_text="Проверка валидации филиала",
        ),
        tenant_scope=tenant_scope,
    )

    with pytest.raises(ValueError, match="does not belong"):
        await LeadService.qualify_lead(
            db,
            lead_id=lead_data["id"],
            payload=LeadQualifyPayload(
                customer_id=customer_a.id,
                customer_branch_id=branch_b.id,
            ),
            tenant_scope=tenant_scope,
        )


@pytest.mark.asyncio
async def test_mark_lost_and_archive_old_leads(db, tenant_scope):
    created = await LeadService.create_lead(
        db,
        LeadCreatePayload(
            source="phone",
            name="Lead Lost",
            phone="+375294444444",
            request_text="Тест потери лида",
        ),
        tenant_scope=tenant_scope,
    )

    updated = await LeadService.mark_lead_lost(
        db,
        lead_id=created["id"],
        payload=LeadLossPayload(status="lost", loss_reason="no_product"),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert updated is not None
    assert updated["status"] == "lost"
    assert updated["loss_reason"] == "no_product"

    lead = await db.get(Lead, created["id"])
    assert lead is not None
    lead.updated_at = datetime.now() - timedelta(days=100)
    db.add(lead)
    await db.commit()

    archived = await LeadService.archive_expired_lost_leads(db, older_than_days=90)
    assert archived == 1

    refreshed = await db.get(Lead, created["id"])
    assert refreshed is not None
    assert refreshed.archived_at is not None

    listed = await LeadService.list_leads(db, page=1, limit=20, tenant_scope=TEST_TENANT_SCOPE)
    ids = [item["id"] for item in listed["items"]]
    assert created["id"] not in ids
