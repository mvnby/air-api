import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer
from models.tenancy import TenantScope
from services.customer_contact_service import CustomerContactService


@pytest.mark.asyncio
async def test_concurrent_primary_contact_changes_leave_one_primary(db_engine):
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        customer = Customer(
            tenant_id=1,
            name="Concurrent contacts",
            phone="+375291234567",
            type="company",
        )
        session.add(customer)
        await session.commit()
        customer_id = int(customer.id)

    async def add_primary(name: str, phone: str):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await CustomerContactService.create_contact(
                session,
                customer_id,
                {"name": name, "phone": phone, "is_primary": True},
                tenant_scope=scope,
                author_name=name,
            )

    results = await asyncio.gather(
        add_primary("Первый контакт", "+375291111111"),
        add_primary("Второй контакт", "+375292222222"),
    )
    assert all(result is not None for result in results)

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        contact_list = await CustomerContactService.list_contacts(
            session, customer_id, tenant_scope=scope
        )
        primaries = [
            contact for contact in contact_list["items"]
            if contact["is_primary"] and contact["is_active"]
        ]
        assert len(primaries) == 1
        stored_customer = await session.get(Customer, customer_id)
        assert stored_customer.phone == primaries[0]["phone"]
