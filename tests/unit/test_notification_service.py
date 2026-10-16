from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from models import StaffUser, TenantMembership, Tenant, Storefront

from core.config import settings
from services.notification_service import NotificationService
from services.tenant_entity_access_service import TenantEntityAccessService

from models.tenancy import TenantScope

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def notification_session():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: SQLModel.metadata.create_all(conn, tables=[
            Tenant.__table__, Storefront.__table__, StaffUser.__table__, TenantMembership.__table__,
        ]))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, slug='mvn', display_name='MVN', is_system=True),
                         Tenant(id=2, slug='partner', display_name='Partner'),
                         Storefront(id=1, tenant_id=1, slug='main', display_name='Main', status='active', is_default=True),
                         Storefront(id=2, tenant_id=2, slug='main', display_name='Partner', status='active', is_default=True)])
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_notification_audience(session, telegram_ids):
    entries = [(telegram_id, 1, role, True, 'active') for telegram_id, role in
               zip(telegram_ids, ('owner', 'admin', 'manager'))]
    # Global owner roles and ADMIN_IDS must not override company membership,
    # catalog-only access, notification opt-out or inactive identity status.
    entries += [(90, 1, 'catalog_editor', True, 'active'),
                (91, 2, 'owner', True, 'active'),
                (92, 1, 'owner', False, 'active'),
                (93, 1, 'owner', True, 'inactive')]
    for telegram_id, tenant_id, role, consent, status in entries:
        user = StaffUser(display_name=f'Staff {telegram_id}', telegram_id=telegram_id,
                         primary_role='owner', roles=['owner'], status=status,
                         telegram_notifications_enabled=consent)
        session.add(user)
        await session.flush()
        session.add(TenantMembership(tenant_id=tenant_id, staff_user_id=user.id, role=role))
    await session.commit()


class _DummyResult:
    def __init__(self, order):
        self._order = order

    def scalar_one_or_none(self):
        return self._order

    def scalars(self):
        return self

    def first(self):
        return self._order

    def all(self):
        return []

    def __iter__(self):
        return iter(self.all())


class _DummySession:
    def __init__(self, order):
        self._order = order
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, _stmt):
        return _DummyResult(self._order)


@pytest.mark.asyncio
async def test_notify_admins_new_order_skips_when_no_admins(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    session = _DummySession(order=None)
    send_mock = AsyncMock()
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    await NotificationService.notify_admins_new_order(
        session=session,
        order_id=1,
        customer_name="User",
        customer_username="user",
        customer_phone="+123",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_new_order_warns_for_missing_order(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    session = _DummySession(order=None)
    send_mock = AsyncMock()
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    with caplog.at_level("WARNING"):
        await NotificationService.notify_admins_new_order(
            session=session,
            order_id=404,
            customer_name="User",
            customer_username="user",
            customer_phone="+123",
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert "NOTIFY_NEW_ORDER_SKIPPED missing_order_id=404" in caplog.text
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_new_order_sends_to_admins(monkeypatch, notification_session):
    monkeypatch.setattr(settings, "ADMIN_IDS", "10,11,90,91,92,93,999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 12, raising=False)

    order = SimpleNamespace(
        id=77,
        total_amount=999,
        user_id=500,
        delivery_address="phone",
        product_links=[
            SimpleNamespace(
                product=SimpleNamespace(title="Model <X>"),
                product_id=1,
                price=500,
                quantity=2,
                is_installation_included=True,
                installation_price=120,
            ),
        ],
    )
    session = notification_session
    await _seed_notification_audience(session, [10, 11, 12])
    monkeypatch.setattr(TenantEntityAccessService, 'get_order', AsyncMock(return_value=order))
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    await NotificationService.notify_admins_new_order(
        session=session,
        order_id=77,
        customer_name="Ivan <script>",
        customer_username="ivan&co",
        customer_phone="<+375291234567>",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert [call.args[0] for call in send_mock.await_args_list] == [10, 11, 12]
    sent_text = send_mock.await_args_list[0].args[1]
    assert "НОВЫЙ ЗАКАЗ #77" in sent_text
    assert "Ivan &lt;script&gt;" in sent_text
    assert "ivan&amp;co" in sent_text
    assert "Model &lt;X&gt; x2" in sent_text
    assert "<script>" not in sent_text
    assert "Монтаж: 120 BYN" in sent_text


@pytest.mark.asyncio
async def test_notify_admins_staff_order_created_counts_only_confirmed_delivery(monkeypatch, caplog, notification_session):
    monkeypatch.setattr(settings, "ADMIN_IDS", "10,11,90,91,92,93,999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    order = SimpleNamespace(
        id=88,
        delivery_address="Победы 15",
        installation_date=None,
        measurement_date=None,
        comment="ТО, Иван, +375 29 123-45-67, Победы 15",
        technical_meta={"service_type": "maintenance"},
        customer=SimpleNamespace(name="Иван", phone="+375 29 123-45-67"),
    )
    session = notification_session
    await _seed_notification_audience(session, [10, 11])
    monkeypatch.setattr(TenantEntityAccessService, 'get_order', AsyncMock(return_value=order))
    send_mock = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr("services.notification_service.BotService.send_rich_message", send_mock)

    with caplog.at_level("WARNING"):
        sent = await NotificationService.notify_admins_staff_order_created(
            session=session,
            order_id=88,
            source_label="Telegram-бот",
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert sent == 1
    assert [call.args[0] for call in send_mock.await_args_list] == [10, 11]
    rich_text = send_mock.await_args_list[0].args[1]
    fallback_text = send_mock.await_args_list[0].kwargs["fallback_text"]
    assert "<h3>Новый рабочий заказ #88</h3>" in rich_text
    assert "<b>Источник:</b> Telegram-бот" in rich_text
    assert "<b>Услуга:</b> Обслуживание" in rich_text
    assert "<b>Клиент:</b> Иван" in rich_text
    assert "Победы 15" in rich_text
    assert "Новый рабочий заказ #88" in fallback_text
    assert "NOTIFY_STAFF_ORDER_DELIVERY_FAILED order_id=88 admin_id=11" in caplog.text


@pytest.mark.asyncio
async def test_notify_admins_work_stage_status_changed_counts_only_confirmed_delivery(monkeypatch, caplog, notification_session):
    monkeypatch.setattr(settings, "ADMIN_IDS", "10,11,90,91,92,93,999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    stage = SimpleNamespace(
        id=5,
        order_id=88,
        name="Монтаж <важно>",
        status="completed",
        start_time=datetime(2026, 6, 15, 14, 0),
        manager_comment="Комментарий менеджера",
        installer_report="Готово <фото>",
        installer=SimpleNamespace(name="Петр"),
        order=SimpleNamespace(
            id=88,
            delivery_address="Победы 15",
            customer=SimpleNamespace(name="Иван", phone="+375 29 123-45-67"),
        ),
    )
    session = notification_session
    await _seed_notification_audience(session, [10, 11])
    monkeypatch.setattr(TenantEntityAccessService, 'get_order_stage', AsyncMock(return_value=stage))
    send_mock = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr("services.notification_service.BotService.send_rich_message", send_mock)

    with caplog.at_level("WARNING"):
        sent = await NotificationService.notify_admins_work_stage_status_changed(session, stage_id=5, tenant_scope=TEST_TENANT_SCOPE)

    assert sent == 1
    assert [call.args[0] for call in send_mock.await_args_list] == [10, 11]
    rich_text = send_mock.await_args_list[0].args[1]
    fallback_text = send_mock.await_args_list[0].kwargs["fallback_text"]
    assert "<h3>Задача #5: выполнена</h3>" in rich_text
    assert "<b>Заказ:</b> #88" in rich_text
    assert "Монтаж &lt;важно&gt;" in rich_text
    assert "<blockquote>Готово &lt;фото&gt;</blockquote>" in rich_text
    assert "<важно>" not in rich_text
    assert "Задача #5: выполнена" in fallback_text
    assert "NOTIFY_WORK_STAGE_STATUS_DELIVERY_FAILED stage_id=5 admin_id=11" in caplog.text
