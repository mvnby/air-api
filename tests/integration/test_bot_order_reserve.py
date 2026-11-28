"""Exercise reservations against the real order and supply tables."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_reserve import (
    BotConfirmReserveRequest, BotCreateReserveRequest, BotMarkReserveRequestSent, BotSetOrderReserveStatus,
)
from core.command_actor import CommandActor
from models import LegacyOwnerAuthState, Order, OrderProductLink, OrderProposal, Product, StaffUser, Storefront, Tenant, TenantMembership
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource, SupplyRequest, SupplyRequestLine
from services.bot_order_reserve import apply_reserve, read_reserve
from services.order_projection_service import OrderProjectionService
from services.supply_request_service import SupplyRequestService


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def seeded(db_engine, tenant_scope, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "ADMIN_USERNAME", "reserve-operator")
    owner = CommandActor(21, "reserve-operator", tenant_scope, channel="telegram")
    member = CommandActor(22, "reserve-manager", tenant_scope, channel="telegram")
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        db.add_all([
            StaffUser(id=21, username=owner.username, display_name="Оператор", primary_role="owner",
                      roles=["owner"], telegram_id=701, telegram_verified_at=datetime.now(timezone.utc)),
            StaffUser(id=22, username=member.username, display_name="Менеджер", primary_role="manager",
                      roles=["manager"], telegram_id=702, telegram_verified_at=datetime.now(timezone.utc)),
            Tenant(id=2, slug="partner", display_name="Партнёр"),
            Storefront(id=2, tenant_id=1, slug="other", display_name="Другая витрина"),
            Product(id=101, title="Модель A", slug="reserve-model-a", price=850),
            Product(id=102, title="Модель B", slug="reserve-model-b", price=950),
            Supplier(id=41, name="Поставщик тестовый", code="reserve-local", default_payment_method="bank"),
            Supplier(id=42, name="Неактивный поставщик", code="reserve-disabled", is_active=False),
        ])
        await db.flush()
        db.add_all([
            TenantMembership(tenant_id=1, staff_user_id=21, role="owner"),
            TenantMembership(tenant_id=1, staff_user_id=22, role="manager"),
            TenantMembership(tenant_id=2, staff_user_id=22, role="manager"),
            Storefront(id=3, tenant_id=2, slug="partner", display_name="Витрина партнёра"),
            SupplierPriceSource(id=111, supplier_id=41, is_active=False),
        ])
        state = await db.get(LegacyOwnerAuthState, 1)
        state.mode, state.owner_staff_user_id = "staff", 21
        await db.flush()
        db.add_all([
            Order(id=51, tenant_id=1, storefront_id=1, status="negotiation", title="Первый заказ"),
            Order(id=52, tenant_id=1, storefront_id=1, status="execution", title="Второй заказ"),
            Order(id=53, tenant_id=1, storefront_id=2, status="negotiation", title="Заказ другой витрины"),
            Order(id=54, tenant_id=2, storefront_id=3, status="negotiation", title="Заказ партнёра"),
            Order(id=55, tenant_id=1, storefront_id=1, status="closed", title="Закрытый заказ"),
            SupplierOffer(id=91, supplier_id=41, external_id="A", title_raw="Модель A на складе",
                          qty=2, wholesale_value=Decimal("608.24"), wholesale_currency="BYN"),
            SupplierOffer(id=92, supplier_id=41, external_id="B", qty=5),
            SupplierOffer(id=93, supplier_id=41, external_id="A-disabled-source", qty=4, source_id=111),
            SupplierOffer(id=94, supplier_id=42, external_id="A-disabled-vendor", qty=4),
            SupplierOffer(id=95, supplier_id=41, external_id="A-disabled-mapping", qty=4),
            SupplierOffer(id=96, supplier_id=41, external_id="A-coming", qty=4, qty_raw="под заказ"),
        ])
        await db.flush()
        db.add_all([
            OrderProposal(id=61, order_id=51, name="Выбранное", is_selected=True),
            OrderProposal(id=62, order_id=51, name="Альтернатива", sort_order=2),
            ProductSupplierMapping(product_id=101, supplier_id=41, external_id="A"),
            ProductSupplierMapping(product_id=102, supplier_id=41, external_id="B"),
            ProductSupplierMapping(product_id=101, supplier_id=41, external_id="A-disabled-source"),
            ProductSupplierMapping(product_id=101, supplier_id=42, external_id="A-disabled-vendor"),
            ProductSupplierMapping(product_id=101, supplier_id=41, external_id="A-disabled-mapping", is_active=False),
            ProductSupplierMapping(product_id=101, supplier_id=41, external_id="A-coming"),
        ])
        await db.flush()
        db.add_all([
            OrderProductLink(id=71, order_id=51, proposal_id=61, product_id=101, quantity=3, price=850, cost=608),
            OrderProductLink(id=72, order_id=51, proposal_id=62, product_id=102, quantity=3, price=950, cost=600),
            OrderProductLink(id=73, order_id=52, product_id=101, quantity=2, price=850, cost=608),
            OrderProductLink(id=74, order_id=53, product_id=101, quantity=1, price=850, cost=608),
            OrderProductLink(id=75, order_id=54, product_id=101, quantity=1, price=850, cost=608),
            OrderProductLink(id=76, order_id=55, product_id=101, quantity=1, price=850, cost=608),
        ])
        await db.commit()
    return owner, member


async def _detail(db, actor, order_id):
    detail = await OrderProjectionService.get_order_detail_for_manager(
        db, order_id, tenant_scope=actor.tenant_scope, repair_legacy_state=False,
    )
    assert detail is not None
    return detail


async def _read(db, actor, order_id=51):
    return await read_reserve(db, actor, await _detail(db, actor, order_id))


async def _apply(db, actor, change, order_id=51):
    await apply_reserve(db, actor, order_id, change, await _detail(db, actor, order_id))


def _create(line_id=71, offer_id=91, quantity=1):
    return BotCreateReserveRequest(kind="create_reserve_request", line_id=line_id, offer_id=offer_id, quantity=quantity)


async def test_actual_supplier_request_and_confirmation_preserve_states_and_only_safe_fields(db, seeded):
    operator, manager = seeded
    state = await _read(db, operator)
    assert state.supplier_access and state.can_set_order_status
    assert [(line.id, line.quantity) for line in state.lines] == [(71, 3)]
    candidate, = state.lines[0].candidates
    assert (candidate.offer_id, candidate.max_quantity) == (91, 2)

    await _apply(db, operator, _create())
    state = await _read(db, operator)
    reserve_line, = state.lines
    draft, = reserve_line.requests
    assert state.manager_status == "pending"
    assert draft.status == "draft" and draft.can_mark_sent and draft.can_confirm
    assert reserve_line.remaining_quantity == 2 and reserve_line.candidates[0].max_quantity == 1
    assert draft.supplier_message == "Здравствуйте! Подтвердите наличие и резерв, пожалуйста: Модель A (код A) — 1 шт."
    assert all(private not in state.model_dump_json() for private in ["608", "wholesale", "unit_cost"])
    request = await db.get(SupplyRequest, draft.request_id)
    item = await db.get(SupplyRequestLine, draft.id)
    assert request.payment_method == "bank" and request.created_by == operator.username
    assert request.supplier_message_sent_at is None
    assert item.order_product_link_id == 71 and item.unit_cost_snapshot == Decimal("608.24")

    mark = BotMarkReserveRequestSent(kind="mark_reserve_request_sent", line_id=71, request_line_id=draft.id)
    with pytest.raises(HTTPException) as foreign_actor:
        await _apply(db, manager, mark)
    assert foreign_actor.value.status_code == 403
    assert (await _read(db, manager)).lines[0].requests == []
    await _apply(db, operator, mark)
    pending, = (await _read(db, operator)).lines[0].requests
    assert pending.status == "awaiting_reply" and not pending.can_mark_sent and pending.can_confirm
    assert request.supplier_message_snapshot == draft.supplier_message and request.supplier_message_sent_at is not None
    with pytest.raises(HTTPException) as already_sent:
        await _apply(db, operator, mark)
    assert already_sent.value.status_code == 409

    confirmation = {"kind": "confirm_reserve_request", "line_id": 71, "request_line_id": draft.id}
    with pytest.raises(ValidationError):
        BotConfirmReserveRequest(**confirmation)
    with pytest.raises(HTTPException) as expired:
        await _apply(db, operator, BotConfirmReserveRequest(
            **confirmation, confirmed=True, reserved_until=datetime.now(timezone.utc) - timedelta(days=1),
        ))
    assert expired.value.status_code == 400
    deadline = datetime.now(timezone.utc) + timedelta(days=1)
    await _apply(db, operator, BotConfirmReserveRequest(**confirmation, confirmed=True, reserved_until=deadline))
    reserved, = (await _read(db, operator)).lines[0].requests
    assert reserved.status == "reserved" and request.status == "reserved" and item.status == "reserved"
    assert reserved.reserved_until == deadline and not reserved.can_confirm
    assert (await db.get(Order, 51)).equipment_status == "pending"
    item.reserved_until -= timedelta(days=2)
    await db.flush()
    freed, = (await _read(db, operator)).lines
    assert freed.requests[0].status == "expired"
    assert freed.remaining_quantity == 3 and freed.candidates[0].max_quantity == 2


async def test_scoped_internal_mark_for_regular_manager_and_fail_closed_supplier_changes(db, seeded):
    operator, manager = seeded
    state = await _read(db, manager)
    assert state.can_set_order_status and not state.supplier_access
    assert state.lines[0].title == "Модель A" and state.lines[0].remaining_quantity is None
    assert "Поставщик тестовый" not in state.model_dump_json()

    reserve = BotSetOrderReserveStatus(kind="set_order_reserve_status", status="reserved")
    release = BotSetOrderReserveStatus(kind="set_order_reserve_status", status="pending")
    await _apply(db, manager, reserve)
    assert (await _read(db, manager)).manager_status == "reserved"
    assert await db.scalar(select(func.count()).select_from(SupplyRequest)) == 0
    await _apply(db, manager, release)
    assert (await _read(db, manager)).manager_status == "pending"

    for change in [_create(line_id=72), _create(line_id=73), _create(offer_id=92),
                   _create(offer_id=93), _create(offer_id=94), _create(offer_id=95),
                   _create(offer_id=96), _create(quantity=3)]:
        with pytest.raises(HTTPException) as stale:
            await _apply(db, operator, change)
        assert stale.value.status_code == 409
    with pytest.raises(HTTPException) as closed:
        await _apply(db, manager, reserve, order_id=55)
    assert closed.value.status_code == 409
    assert not (await _read(db, manager, 55)).can_set_order_status
    with pytest.raises(HTTPException) as absent:
        await apply_reserve(db, manager, 53, reserve, await _detail(db, manager, 51))
    assert absent.value.status_code == 404

    demo = replace(manager, tenant_scope=replace(manager.tenant_scope, demo_read_only=True))
    assert not (await _read(db, demo)).can_set_order_status
    with pytest.raises(HTTPException) as denied:
        await _apply(db, demo, reserve)
    assert denied.value.status_code == 403

    partner = replace(manager, tenant_scope=replace(manager.tenant_scope, tenant_id=2, storefront_id=3, is_system=False))
    partner_state = await _read(db, partner, 54)
    assert partner_state.can_set_order_status and not partner_state.supplier_access
    await _apply(db, partner, reserve, 54)
    assert (await db.get(Order, 54)).equipment_status == "reserved"


async def test_concurrent_orders_cannot_promise_the_same_imported_stock(db_engine, seeded):
    operator, _ = seeded

    async def reserve(order_id, line_id):
        async with AsyncSession(db_engine, expire_on_commit=False) as db:
            async with db.begin():
                await _apply(db, operator, _create(line_id=line_id, quantity=2), order_id)

    outcomes = await asyncio.gather(reserve(51, 71), reserve(52, 73), return_exceptions=True)
    assert outcomes.count(None) == 1
    failed, = [error for error in outcomes if error is not None]
    assert isinstance(failed, HTTPException) and failed.status_code == 409, outcomes
    async with AsyncSession(db_engine) as db:
        assert await db.scalar(select(func.count()).select_from(SupplyRequestLine)) == 1
        assert await db.scalar(select(SupplyRequestLine.qty)) == 2


@pytest.mark.parametrize("same_line", [True, False])
async def test_manager_and_telegram_share_reservation_capacity(db_engine, seeded, same_line):
    operator, _ = seeded
    quantity = 1 if same_line else 2
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        (await db.get(OrderProductLink, 71)).quantity = quantity
        (await db.get(SupplierOffer, 91)).qty = 5 if same_line else quantity
        await db.commit()

    async def manager_reserve():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await SupplyRequestService.create_from_order_lines(
                session,
                {"order_product_link_ids": [71 if same_line else 73], "intent": "reserve", "supplier_id": 41},
                tenant_scope=operator.tenant_scope, created_by=operator.username,
            )

    async def telegram_reserve():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            async with session.begin():
                await _apply(session, operator, _create(quantity=quantity))

    results = await asyncio.gather(manager_reserve(), telegram_reserve(), return_exceptions=True)
    (error,) = [result for result in results if isinstance(result, Exception)]
    if isinstance(error, ValueError):
        assert ("изменилось количество без заявки" if same_line else "изменился доступный остаток") in str(error)
    else:
        assert isinstance(error, HTTPException) and error.status_code == 409, results
    async with AsyncSession(db_engine) as db:
        assert await db.scalar(select(func.count()).select_from(SupplyRequestLine)) == 1
        assert await db.scalar(select(SupplyRequestLine.qty)) == quantity


async def test_order_endpoint_races_retry_and_rejects_stale_supplier_offer(db_engine, seeded, monkeypatch):
    from core.config import settings
    from core.database import get_session
    from routers.internal_bot_order_desk import router

    async def database():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = database
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "test-order-reservation")
    actor = {"telegram_id": 701, "expected_context_version": 0}
    url = "/api/internal/bot/v1/order-desk/51"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"Authorization": "Bearer test-order-reservation"}) as client:
        response = await client.get(url, params=actor)
        assert response.status_code == 200, response.text
        desk = response.json()
        assert desk["reserve"]["supplier_access"] is True
        payload = {**actor, "expected_revision": desk["revision"], "idempotency_key": str(uuid4()),
                   "change": _create().model_dump()}
        responses = await asyncio.gather(*(client.post(url + "/commands", json=payload) for _ in range(2)))
        assert [result.status_code for result in responses] == [200, 200], [result.text for result in responses]
        with_draft = responses[0].json()
        (draft,) = with_draft["reserve"]["lines"][0]["requests"]
        assert responses[1].json() == with_draft and draft["status"] == "draft"
        stale = await client.post(url + "/commands", json={**payload, "idempotency_key": str(uuid4())})
        assert stale.status_code == 409
        async with AsyncSession(db_engine) as db:
            assert await db.scalar(select(func.count()).select_from(SupplyRequestLine)) == 1
            (await db.get(SupplierOffer, 91)).is_active = False
            await db.commit()
        mark = {"kind": "mark_reserve_request_sent", "line_id": 71, "request_line_id": draft["id"]}
        changed = {**payload, "idempotency_key": str(uuid4()), "expected_revision": with_draft["revision"], "change": mark}
        assert (await client.post(url + "/commands", json=changed)).status_code == 409
        refreshed = (await client.get(url, params=actor)).json()
        assert refreshed["reserve"]["lines"][0]["requests"][0]["can_mark_sent"] is False
        assert refreshed["reserve"]["lines"][0]["candidates"] == []
