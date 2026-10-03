from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from models import Customer, CustomerContact
from models.tenancy import Tenant, TenantScope
from services.customer_contact_service import CustomerContactService
from services.customer_service import CustomerService


@pytest.fixture
async def contact_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'contacts.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Tenant(id=1, slug="one", display_name="One", kind="independent_seller"))
        session.add(Tenant(id=2, slug="two", display_name="Two", kind="independent_seller"))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_fallback_survives_secondary_contact_and_primary_updates(contact_session):
    customer = Customer(
        tenant_id=1,
        name="ООО Пример",
        phone="+375 (29) 111-22-33",
        email="old@example.com",
        full_legal_name="Общество с ограниченной ответственностью Пример",
        type="company",
    )
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)

    fallback = await CustomerContactService.list_contacts(
        contact_session, int(customer.id), tenant_scope=scope
    )
    assert fallback["items"][0]["id"] is None
    assert fallback["items"][0]["name"] is None
    assert fallback["items"][0]["is_legacy"] is True
    assert fallback["items"][0]["phone"] == customer.phone

    secondary = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Второй контакт", "phone": "+375291234567", "is_primary": False},
        tenant_scope=scope,
        author_id=17,
        author_name="Менеджер",
    )
    await contact_session.refresh(customer)
    assert customer.phone == "+375 (29) 111-22-33"
    assert customer.email == "old@example.com"
    assert secondary["is_primary"] is False
    actual_contacts = (
        await contact_session.execute(
            select(CustomerContact).where(CustomerContact.customer_id == customer.id)
        )
    ).scalars().all()
    assert len(actual_contacts) == 2
    legacy = next(contact for contact in actual_contacts if contact.is_legacy)
    assert legacy.is_primary is True
    assert legacy.name is None

    await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(secondary["id"]),
        {"is_primary": True},
        tenant_scope=scope,
        author_id=17,
        author_name="Менеджер",
    )
    await contact_session.refresh(customer)
    assert customer.phone == "+375291234567"
    assert customer.email is None
    primaries = [contact for contact in actual_contacts if contact.is_primary]
    assert len(primaries) == 1
    assert primaries[0].id == secondary["id"]

    later = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Поздний контакт", "phone": "+375293333333"},
        tenant_scope=scope,
    )
    # Exercise switching to a newer row and back to an older row, which used
    # to violate the partial unique index when updates flushed in ID order.
    await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(later["id"]),
        {"is_primary": True},
        tenant_scope=scope,
    )
    await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(secondary["id"]),
        {"is_primary": True},
        tenant_scope=scope,
    )
    await contact_session.refresh(customer)
    assert customer.phone == "+375291234567"
    actual_contacts = (
        await contact_session.execute(
            select(CustomerContact).where(CustomerContact.customer_id == customer.id)
        )
    ).scalars().all()
    primaries = [contact for contact in actual_contacts if contact.is_primary and contact.is_active]
    assert [contact.id for contact in primaries] == [secondary["id"]]

    history = await CustomerContactService.history(
        contact_session, int(customer.id), tenant_scope=scope, page=1, limit=100
    )
    assert history["meta"]["total"] >= 2
    assert any(
        row["field_name"] == "is_primary"
        and row["old_value"] == "False"
        and row["new_value"] == "True"
        and row["author_name"] == "Менеджер"
        for row in history["items"]
    )


@pytest.mark.asyncio
async def test_contact_reads_and_search_are_customer_and_tenant_scoped(contact_session):
    customer = Customer(
        tenant_id=1,
        name="Клиент",
        phone="+375291111111",
        email=None,
        full_legal_name="Полное юридическое название",
        type="company",
    )
    foreign_customer = Customer(
        tenant_id=2,
        name="Другой клиент",
        phone="+375292222222",
        type="company",
    )
    contact_session.add_all([customer, foreign_customer])
    await contact_session.commit()
    await contact_session.refresh(customer)
    await contact_session.refresh(foreign_customer)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    foreign_scope = TenantScope(tenant_id=2, storefront_id=2)

    created = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {
            "name": "Анна Петрова",
            "phone": "+375 (29) 987-65-43",
            "email": "anna@example.com",
            "is_primary": True,
        },
        tenant_scope=scope,
    )

    assert await CustomerContactService.list_contacts(
        contact_session, int(customer.id), tenant_scope=foreign_scope
    ) is None
    assert await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(created["id"]),
        {"name": "Чужая правка"},
        tenant_scope=foreign_scope,
    ) is None

    by_name = await CustomerService.list_for_manager(
        contact_session,
        page=1,
        limit=20,
        search="Анна Петрова",
        only_with_orders=False,
        tenant_scope=scope,
    )
    assert [row["id"] for row in by_name["items"]] == [customer.id]
    by_digits = await CustomerService.list_for_manager(
        contact_session,
        page=1,
        limit=20,
        search="9876543",
        only_with_orders=False,
        tenant_scope=scope,
    )
    assert [row["id"] for row in by_digits["items"]] == [customer.id]
    by_legal_name = await CustomerService.list_for_manager(
        contact_session,
        page=1,
        limit=20,
        search="юридическое название",
        only_with_orders=False,
        tenant_scope=scope,
    )
    assert [row["id"] for row in by_legal_name["items"]] == [customer.id]
    listed = by_name["items"][0]
    assert listed["contact_count"] == 1
    assert listed["primary_contact"]["id"] == created["id"]

    await CustomerService.update_for_manager(
        contact_session,
        customer_id=int(customer.id),
        payload={"is_favorite": True, "is_archived": True},
        tenant_scope=scope,
    )
    hidden = await CustomerService.list_for_manager(
        contact_session,
        page=1,
        limit=20,
        search=None,
        only_with_orders=False,
        tenant_scope=scope,
    )
    assert hidden["items"] == []
    archived_favorites = await CustomerService.list_for_manager(
        contact_session,
        page=1,
        limit=20,
        search=None,
        only_with_orders=False,
        only_favorites=True,
        include_archived=True,
        tenant_scope=scope,
    )
    assert [row["id"] for row in archived_favorites["items"]] == [customer.id]


@pytest.mark.asyncio
async def test_partial_index_rejects_two_primary_contacts(contact_session):
    customer = Customer(tenant_id=1, name="Клиент", phone="111", type="company")
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    contact_session.add_all(
        [
            CustomerContact(customer_id=customer.id, name="Первый", is_primary=True),
            CustomerContact(customer_id=customer.id, name="Второй", is_primary=True),
        ]
    )
    with pytest.raises(IntegrityError):
        await contact_session.commit()
    await contact_session.rollback()


@pytest.mark.asyncio
async def test_first_primary_edit_reuses_virtual_legacy_fallback(contact_session):
    customer = Customer(
        tenant_id=1,
        name="Компания",
        phone="+375291234567",
        email="legacy@example.com",
        type="company",
    )
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)

    created = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Анна Иванова", "phone": "+375299876543", "is_primary": True},
        tenant_scope=scope,
        author_name="Менеджер",
    )
    await contact_session.refresh(customer)
    contacts = (
        await contact_session.execute(
            select(CustomerContact).where(CustomerContact.customer_id == customer.id)
        )
    ).scalars().all()
    assert len(contacts) == 1
    assert created["id"] == contacts[0].id
    assert contacts[0].name == "Анна Иванова"
    assert contacts[0].is_legacy is False
    assert contacts[0].email == "legacy@example.com"
    assert customer.phone == "+375299876543"
    assert customer.email == "legacy@example.com"


@pytest.mark.asyncio
async def test_last_primary_cannot_be_deactivated_but_replacement_is_promoted(contact_session):
    customer = Customer(
        tenant_id=1,
        name="Компания",
        phone="+375291234567",
        email="legacy@example.com",
        type="company",
    )
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    primary = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Первый", "is_primary": True},
        tenant_scope=scope,
    )
    with pytest.raises(ValueError, match="Сначала выберите другое"):
        await CustomerContactService.patch_contact(
            contact_session,
            int(customer.id),
            int(primary["id"]),
            {"is_primary": False, "is_active": False},
            tenant_scope=scope,
        )
    await contact_session.refresh(customer)
    assert customer.phone == "+375291234567"

    secondary = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Второй", "phone": "+375290000000"},
        tenant_scope=scope,
    )
    # Idempotently leaving a nonprimary contact nonprimary must be accepted.
    await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(secondary["id"]),
        {"is_primary": False},
        tenant_scope=scope,
    )
    await CustomerContactService.patch_contact(
        contact_session,
        int(customer.id),
        int(primary["id"]),
        {"is_primary": False, "is_active": False},
        tenant_scope=scope,
    )
    await contact_session.refresh(customer)
    assert customer.phone == "+375290000000"
    listing = await CustomerContactService.list_contacts(
        contact_session, int(customer.id), tenant_scope=scope
    )
    assert [item["id"] for item in listing["items"] if item["is_primary"]] == [secondary["id"]]


@pytest.mark.asyncio
async def test_customer_summary_does_not_show_inactive_contact_as_fallback(contact_session):
    customer = Customer(
        tenant_id=1,
        name="Компания",
        phone="stale legacy phone",
        type="company",
    )
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    contact_session.add(
        CustomerContact(
            customer_id=customer.id,
            name="Неактивный контакт",
            phone="old phone",
            is_primary=True,
            is_active=False,
        )
    )
    await contact_session.commit()

    summary = await CustomerService.get_for_manager(
        contact_session,
        int(customer.id),
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
    )
    assert summary["primary_contact"] is None


@pytest.mark.asyncio
async def test_legacy_customer_patch_syncs_only_the_primary_contact(contact_session):
    customer = Customer(
        tenant_id=1,
        name="Компания",
        phone="+375291234567",
        email="legacy@example.com",
        type="company",
    )
    contact_session.add(customer)
    await contact_session.commit()
    await contact_session.refresh(customer)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    primary = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Первый", "phone": customer.phone, "email": customer.email, "is_primary": True},
        tenant_scope=scope,
    )
    secondary = await CustomerContactService.create_contact(
        contact_session,
        int(customer.id),
        {"name": "Второй", "phone": "+375299999999", "email": "secondary@example.com"},
        tenant_scope=scope,
    )

    updated = await CustomerService.update_for_manager(
        contact_session,
        customer_id=int(customer.id),
        payload={"phone": "+375290000000", "email": "updated@example.com"},
        tenant_scope=scope,
    )
    assert updated["phone"] == "+375290000000"
    assert updated["email"] == "updated@example.com"
    contacts = (
        await contact_session.execute(
            select(CustomerContact).where(CustomerContact.customer_id == customer.id)
        )
    ).scalars().all()
    by_id = {contact.id: contact for contact in contacts}
    assert by_id[primary["id"]].phone == "+375290000000"
    assert by_id[primary["id"]].email == "updated@example.com"
    assert by_id[secondary["id"]].phone == "+375299999999"
    assert by_id[secondary["id"]].email == "secondary@example.com"
