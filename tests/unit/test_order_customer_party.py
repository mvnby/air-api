import pytest

from models import Customer, CustomerType, LeadSource
from services.order_service import OrderService


@pytest.mark.asyncio
async def test_order_service_creates_and_explicitly_converts_customer_party_type(
    db,
    tenant_scope,
):
    created_order = await OrderService.create_from_website(
        session=db,
        tenant_scope=tenant_scope,
        customer_name="ИП Тест",
        customer_phone="+375291234567",
        customer_email=None,
        customer_address="Минск",
        items=[],
        lead_source=LeadSource.MANAGER,
        customer_type="individual_entrepreneur",
        customer_inn="123456789",
        customer_full_legal_name="ИП Тест",
    )
    customer = await db.get(Customer, created_order.customer_id)

    assert customer is not None
    assert customer.type == CustomerType.individual_entrepreneur
    assert customer.signing_mode == "self"

    await OrderService.create_from_website(
        session=db,
        tenant_scope=tenant_scope,
        customer_name="ООО Тест",
        customer_phone="+375291234567",
        customer_email=None,
        customer_address="Минск",
        items=[],
        lead_source=LeadSource.MANAGER,
        customer_id=customer.id,
        customer_type="company",
        customer_inn="123456789",
        customer_full_legal_name="ООО Тест",
    )
    await db.refresh(customer)

    assert customer.type == CustomerType.company
    assert customer.signing_mode == "statutory_body"

    await OrderService.create_from_website(
        session=db,
        tenant_scope=tenant_scope,
        customer_name="ООО Тест",
        customer_phone="+375291234567",
        customer_email=None,
        customer_address="Минск",
        items=[],
        lead_source=LeadSource.MANAGER,
        customer_id=customer.id,
    )
    await db.refresh(customer)

    assert customer.type == CustomerType.company
    assert customer.signing_mode == "statutory_body"
