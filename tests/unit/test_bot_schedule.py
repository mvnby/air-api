from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from models import Customer, CustomerBranch, CustomerEquipment, Order, OrderWorkStage, StaffUser, Tenant
from routers.internal_bot_schedule import router
from services.bot_access_service import BotAccessService
from services.bot_quick_order_service import BotQuickOrderService
from services.bot_schedule_service import read_manager_schedule
from services.bot_staff_selection_service import BotStaffSelectionService
from services.order_service import OrderService
from tests.unit.test_bot_staff_selection import selected_db as selected_db


PATH = "/api/internal/bot/v1/calendar/schedule"
ACTOR = {"telegram_id": 101, "expected_context_version": 0}


async def test_schedule_uses_minsk_days_and_scoped_manager_sources(selected_db, monkeypatch):
    session, _ = selected_db
    initial = await BotAccessService.get_context(session, 101)
    await BotStaffSelectionService.select(
        session, initial.selection, tenant_id=11, storefront_slug="second", expected_version=0,
    )
    monkeypatch.setattr(settings, "MANAGER_BASE_URL", "https://staff.example/manager/")
    session.add_all([
        Customer(id=1, tenant_id=11, name="Лена", phone="+37500001", actual_address="Склад 1"),
        Customer(id=2, tenant_id=12, name="Чужая компания", phone="+37500002"),
        CustomerBranch(id=21, customer_id=2, delivery_address="Чужой адрес"),
    ])
    await session.flush()
    midnight = datetime(2027, 1, 1)
    session.add_all([
        Order(id=100, tenant_id=11, storefront_id=22, customer_id=1, delivery_address="Дом 12",
              measurement_date=midnight, installation_date=datetime(2027, 1, 2, 23, 59, 59, 999999)),
        Order(id=101, tenant_id=11, storefront_id=21, customer_id=1, installation_date=midnight),
        Order(id=102, tenant_id=12, storefront_id=23, customer_id=2, installation_date=midnight),
        Order(id=103, tenant_id=11, storefront_id=22, customer_id=1,
              measurement_date=datetime(2026, 12, 31, 23, 59, 59, 999999), installation_date=datetime(2027, 1, 3)),
    ])
    await session.flush()
    session.add_all([
        OrderWorkStage(id=81, order_id=100, name="Доставка", start_time=datetime(2027, 1, 1, 9, 5, 40)),
        OrderWorkStage(id=85, order_id=100, name="Приёмка", start_time=datetime(2027, 1, 1, 9, 5, 2)),
        OrderWorkStage(id=82, order_id=100, name="Другой день", start_time=datetime(2027, 1, 3)),
        CustomerEquipment(id=90, customer_id=1, customer_branch_id=21, source_order_id=101,
                          installed_at=datetime(2026, 11, 30, 16), maintenance_interval_months=1, maintenance_enabled=True),
        CustomerEquipment(id=91, customer_id=1, installed_at=datetime(2026, 12, 2, 18),
                          maintenance_interval_months=1, maintenance_enabled=True),
        CustomerEquipment(id=92, customer_id=2, installed_at=datetime(2026, 11, 30),
                          maintenance_interval_months=1, maintenance_enabled=True),
    ])
    await session.commit()

    schedule = await read_manager_schedule(
        session, telegram_id=101, now=datetime(2026, 12, 31, 21, 5, tzinfo=timezone.utc),
    )
    data = schedule.model_dump(mode="json")
    assert (data["timezone"], data["today"], data["tomorrow"]) == ("Europe/Minsk", "2027-01-01", "2027-01-02")
    assert [(e["id"], e["date"], e["time"]) for e in data["events"]] == [
        ("equipment-90-maintenance", "2027-01-01", None),
        ("100-measurement", "2027-01-01", "00:00"),
        ("100-stage-85", "2027-01-01", "09:05"),
        ("100-stage-81", "2027-01-01", "09:05"),
        ("equipment-91-maintenance", "2027-01-02", None),
        ("100-installation", "2027-01-02", "23:59"),
    ]
    overdue, measurement, earlier_stage, stage, scheduled, installation = data["events"]
    assert (overdue["status"], overdue["due_date"], overdue["address"]) == ("overdue", "2026-12-30", "Склад 1")
    assert (scheduled["status"], scheduled["due_date"]) == ("scheduled", "2027-01-02")
    assert all(e["order_id"] is None and e["order_url"] is None for e in [overdue, scheduled])
    assert stage["title"] == "Доставка - Лена"
    for event in [measurement, earlier_stage, stage, installation]:
        assert event["order_id"] == 100 and event["due_date"] is None
        assert event["order_url"] == "https://staff.example/manager/orders/100?company=11&site=second"
        assert (event["customer_name"], event["customer_phone"], event["address"]) == ("Лена", "+37500001", "Дом 12")


async def test_requested_day_is_only_shown_after_appointment_is_booked(selected_db, monkeypatch):
    session, _ = selected_db
    context = await BotAccessService.get_context(session, 101)
    customer = Customer(tenant_id=context.selection.tenant_id, name="Лена", phone="+37500001")
    session.add(customer)
    await session.commit()
    monkeypatch.setattr(
        "services.bot_quick_order_service.NotificationService.notify_admins_staff_order_created", AsyncMock(),
    )
    requested = datetime(2027, 1, 1)
    result = await BotQuickOrderService.create_order_from_draft(
        session,
        {"customer_id": customer.id, "name": customer.name, "workflow_type": "maintenance",
         "service_type": "maintenance", "request_text": "Обслуживание в этот день",
         "target_date": requested.isoformat(), "target_date_precision": "date"},
        tenant_scope=context.selection.scope,
    )
    order = await session.get(Order, result["id"])
    assert order.technical_meta["requested_date_precision"] == "date"
    assert not (await read_manager_schedule(session, telegram_id=101, now=requested)).events

    order.installation_date = requested
    await session.commit()
    booked = await read_manager_schedule(session, telegram_id=101, now=requested)
    assert [(event.type, event.time) for event in booked.events] == [("installation", "00:00")]


async def test_empty_schedule_on_both_sides_of_local_midnight(selected_db):
    session, _ = selected_db
    for utc_hour, utc_minute, today, tomorrow in [
        (20, 59, "2026-12-31", "2027-01-01"),
        (21, 0, "2027-01-01", "2027-01-02"),
    ]:
        schedule = await read_manager_schedule(
            session, telegram_id=101, now=datetime(2026, 12, 31, utc_hour, utc_minute, tzinfo=timezone.utc),
        )
        assert schedule.model_dump(mode="json") == {
            "today": today, "tomorrow": tomorrow, "timezone": "Europe/Minsk", "events": [],
        }


@pytest.fixture
async def schedule_client(selected_db, monkeypatch):
    _, engine = selected_db
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "schedule-test-service-token")

    async def database():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_schedule_http_access_requires_current_manager_and_version(schedule_client, selected_db):
    session, _ = selected_db
    client = schedule_client
    assert (await client.post(PATH, json=ACTOR)).status_code == 401
    client.headers["Authorization"] = "Bearer schedule-test-service-token"
    assert (await client.post(PATH, json={**ACTOR, "telegram_id": 999})).status_code == 403
    assert (await client.post(PATH, json={"telegram_id": 101})).status_code == 422
    assert (await client.post(PATH, json={**ACTOR, "storefront_id": 23})).status_code == 422
    tenant = await session.get(Tenant, 11)
    tenant.demo_read_only = True
    await session.commit()
    response = await client.post(PATH, json=ACTOR)
    assert response.status_code == 200 and response.json()["events"] == []

    current = await BotAccessService.get_context(session, 101)
    await BotStaffSelectionService.select(
        session, current.selection, tenant_id=12, storefront_slug="partner", expected_version=0,
    )
    assert (await client.post(PATH, json=ACTOR)).status_code == 409
    # Global roles include "owner", but this tenant gave the actor a catalog-only membership.
    assert (await client.post(PATH, json={**ACTOR, "expected_context_version": 1})).status_code == 403
    partner = await BotAccessService.get_context(session, 101)
    await BotStaffSelectionService.select(
        session, partner.selection, tenant_id=11, storefront_slug="main", expected_version=1,
    )
    user = await session.get(StaffUser, 31)
    user.status = "inactive"
    await session.commit()
    assert (await client.post(PATH, json={**ACTOR, "expected_context_version": 2})).status_code == 403


async def test_switch_during_schedule_read_rejects_the_old_projection(schedule_client, selected_db, monkeypatch):
    _, engine = selected_db
    original = OrderService.get_calendar_events

    async def read_then_switch(session, *args, **kwargs):
        events = await original(session, *args, **kwargs)
        async with AsyncSession(engine, expire_on_commit=False) as concurrent:
            current = await BotAccessService.get_context(concurrent, 101)
            await BotStaffSelectionService.select(
                concurrent, current.selection, tenant_id=11, storefront_slug="second", expected_version=0,
            )
        return events

    monkeypatch.setattr(OrderService, "get_calendar_events", staticmethod(read_then_switch))
    response = await schedule_client.post(PATH, json=ACTOR, headers={"Authorization": "Bearer schedule-test-service-token"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "bot_context_changed"
