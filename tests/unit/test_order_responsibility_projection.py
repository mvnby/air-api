"""Personal order queues preserve company/site boundaries and historical people."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from models import Customer, CustomerType, Order, OrderProposal, OrderStatus, StaffUser
from models.tenancy import Storefront, Tenant, TenantMembership, TenantScope
from routers.manager_orders_read import router
from schemas import ManagerOrderListResponse
from services.order_projection_service import OrderProjectionService
from services.order_service import OrderService


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def responsibility_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'responsibility-projection.db'}")

    @event.listens_for(engine.sync_engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([
            Tenant(id=1, slug='mvn', display_name='MVN', is_system=True),
            Tenant(id=2, slug='partner', display_name='Partner'),
        ])
        await session.flush()
        session.add_all([
            Storefront(id=1, tenant_id=1, slug='main', display_name='Main', is_default=True),
            Storefront(id=2, tenant_id=2, slug='main', display_name='Partner', is_default=True),
            Storefront(id=3, tenant_id=1, slug='second', display_name='Second'),
            StaffUser(id=101, display_name='Вадим', username='vadim-projection', primary_role='manager', roles=['manager'], avatar_version='a' * 64),
            StaffUser(id=102, display_name='Другой менеджер', primary_role='admin', roles=['admin']),
            StaffUser(id=103, display_name='Бывший менеджер', status='inactive', primary_role='manager', roles=['manager']),
            StaffUser(id=201, display_name='Партнёр', primary_role='owner', roles=['owner']),
        ])
        await session.flush()
        session.add_all([
            TenantMembership(id=101, tenant_id=1, staff_user_id=101, role='manager'),
            TenantMembership(id=102, tenant_id=1, staff_user_id=102, role='admin'),
            TenantMembership(id=103, tenant_id=1, staff_user_id=103, role='manager', status='disabled'),
            TenantMembership(id=201, tenant_id=2, staff_user_id=201, role='owner'),
            Customer(id=1001, tenant_id=1, name='Клиент', phone='1001'),
            Customer(id=1002, tenant_id=1, name='Компания', phone='1002', type=CustomerType.company),
            Customer(id=2001, tenant_id=2, name='Другой клиент', phone='2001'),
        ])
        await session.flush()
        now = datetime.now()
        data = [
            (11, 1, 1, 1001, 101, OrderStatus.NEGOTIATION, 'Мой кондиционер'),
            (12, 1, 1, 1002, 101, OrderStatus.EXECUTION, 'Моё обслуживание'),
            (13, 1, 1, 1001, 102, OrderStatus.NEGOTIATION, 'Чужой кондиционер'),
            (14, 1, 1, None, None, OrderStatus.NEGOTIATION, 'Без ответственного'),
            (15, 1, 3, 1001, 101, OrderStatus.NEGOTIATION, 'Другой сайт'),
            (16, 2, 2, 2001, 201, OrderStatus.NEGOTIATION, 'Другая компания'),
            (17, 1, 1, 1001, 103, OrderStatus.NEGOTIATION, 'Сохранённая история'),
            (18, 1, 1, 1001, 101, OrderStatus.NEW_LEAD, 'Входящая заявка'),
        ]
        for index, (oid, tenant, site, customer, person, status, title) in enumerate(data):
            session.add(Order(id=oid, tenant_id=tenant, storefront_id=site,
                customer_id=customer, responsible_staff_user_id=person, responsible_version=2 if oid == 11 else 0,
                status=status, title=title, created_at=now + timedelta(minutes=index),
                next_followup_date=now - timedelta(days=1) if oid == 12 else None))
        await session.flush()
        session.add_all([OrderProposal(order_id=row[0], name='Основное', is_selected=True) for row in data])
        await session.commit()
        yield session
    await engine.dispose()


async def orders(session, **filters):
    result = await OrderProjectionService.get_orders_for_manager(
        session, 'all', 1, 100, tenant_scope=SCOPE, **filters,
    )
    return ManagerOrderListResponse.model_validate(result)


@pytest.mark.asyncio
async def test_mine_filters_count_before_pagination_and_excludes_other_sites(responsibility_session):
    result = await OrderProjectionService.get_orders_for_manager(
        responsibility_session, 'all', 1, 1, tenant_scope=SCOPE,
        assigned_to_me=True, staff_user_id=101, sort='created_at_asc',
    )
    body = ManagerOrderListResponse.model_validate(result)
    assert body.meta.total == 2 and body.meta.pages == 2
    assert [item.id for item in body.items] == [11]
    assert body.items[0].responsible_person.staff_user_id == 101
    assert body.items[0].responsible_person.display_name == 'Вадим'
    assert 'tenant_id=1' in body.items[0].responsible_person.avatar_url
    assert body.items[0].responsible_version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('filters,expected', [
    ({'search': 'кондиционер'}, [11]),
    ({'status': 'execution'}, [12]),
    ({'customer_id': 1001}, [11]),
    ({'overdue_only': True}, [12]),
])
async def test_mine_combines_with_existing_filters(responsibility_session, filters, expected):
    body = await orders(responsibility_session, assigned_to_me=True, staff_user_id=101, **filters)
    assert sorted(item.id for item in body.items) == expected
    assert body.meta.total == len(expected)


@pytest.mark.asyncio
async def test_mine_preserves_business_segment_and_compatibility_delegate(responsibility_session):
    result = await OrderService.get_orders_for_manager(
        responsibility_session, 'b2b', 1, 100, tenant_scope=SCOPE,
        assigned_to_me=True, staff_user_id=101,
    )
    body = ManagerOrderListResponse.model_validate(result)
    assert [item.id for item in body.items] == [12]
    assert body.meta.total == 1


@pytest.mark.asyncio
async def test_no_staff_identity_does_not_turn_mine_into_unassigned(responsibility_session):
    body = await orders(responsibility_session, assigned_to_me=True, staff_user_id=None)
    assert body.items == [] and body.meta.total == 0
    all_orders = await orders(responsibility_session)
    assert {item.id for item in all_orders.items} == {11, 12, 13, 14, 17}
    historical = next(item for item in all_orders.items if item.id == 17)
    assert historical.responsible_person.display_name == 'Бывший менеджер'
    assert historical.responsible_person.is_active is False
    assert next(item for item in all_orders.items if item.id == 14).responsible_person is None


@pytest.mark.asyncio
async def test_responsible_detail_matches_list_without_reassigning_history(responsibility_session):
    detail = await OrderProjectionService.get_order_detail_for_manager(
        responsibility_session, 17, tenant_scope=SCOPE,
    )
    person = detail['responsible_person']
    assert person.staff_user_id == 103 and not person.is_active
    assert (await responsibility_session.get(Order, 17)).responsible_staff_user_id == 103
    assert detail['responsible_version'] == 0


@pytest.mark.asyncio
async def test_http_mine_uses_authenticated_person_and_bounds_page(responsibility_session):
    app = FastAPI()
    app.include_router(router)

    async def current_session():
        yield responsibility_session

    async def current_auth():
        return AuthenticatedUser(username='vadim-projection', auth_source='staff_password',
            staff_user_id=101, role='manager', tenant_id=1, storefront_id=1,
            tenant_membership_id=101, is_system_tenant=True, auth_version=1)

    app.dependency_overrides[get_session] = current_session
    app.dependency_overrides[get_current_auth_context] = current_auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/manager/orders?segment=all&assigned_to_me=true&staff_user_id=102&limit=1')
        assert response.status_code == 200
        data = response.json()
        assert data['meta']['total'] == 2 and len(data['items']) == 1
        assert data['items'][0]['responsible_person']['staff_user_id'] == 101
        too_many = await client.get('/api/manager/orders?limit=101')
        assert too_many.status_code == 422
