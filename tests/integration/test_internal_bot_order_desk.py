"""Exercise the real bot order endpoints, including retries on independent connections."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from models import Customer, Order, OrderProductLink, OrderProposal, OrderServiceLink, StaffUser, Storefront, Tenant, TenantMembership
from models.command_audit import CommandAuditEvent
from routers.internal_bot_order_desk import router


BASE = "/api/internal/bot/v1/order-desk"
ACTOR = {"telegram_id": 501, "expected_context_version": 0}


@pytest.fixture
async def orders(db_engine, monkeypatch):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        db.add_all([Tenant(id=2, slug="second", display_name="Другая фирма"),
                    StaffUser(id=21, telegram_id=501, username="desk-a", display_name="Анна", primary_role="owner"),
                    StaffUser(id=22, telegram_id=502, username="desk-b", display_name="Иван", primary_role="installer")])
        await db.flush()
        db.add_all([TenantMembership(tenant_id=1, staff_user_id=21, role="owner"),
                    TenantMembership(tenant_id=1, staff_user_id=22, role="installer"),
                    Storefront(id=2, tenant_id=1, slug="other", display_name="Другая витрина"),
                    Storefront(id=3, tenant_id=2, slug="second", display_name="Вторая"),
                    Customer(id=65, tenant_id=2, name="Клиент другой компании", phone="+375291110065")])
        await db.flush()
        db.add_all([Order(id=10, tenant_id=1, storefront_id=1, status="negotiation", title="Офис",
                          comment="Внутренняя заметка менеджера"),
                    Order(id=11, tenant_id=1, storefront_id=2, status="negotiation"),
                    Order(id=12, tenant_id=2, storefront_id=3, customer_id=65, status="negotiation"),
                    Order(id=13, tenant_id=1, storefront_id=1, status="negotiation"),
                    Order(id=14, tenant_id=1, storefront_id=1, status="new_lead")])
        await db.flush()
        db.add_all([OrderProposal(id=31, order_id=10, name="Первый", is_selected=True),
                    OrderProposal(id=32, order_id=10, name="Альтернатива", sort_order=2)])
        await db.flush()
        db.add_all([OrderProductLink(id=41, order_id=10, proposal_id=31, title_snapshot="Настенный А", quantity=2, price=810, cost=139),
                    OrderServiceLink(id=43, order_id=10, proposal_id=31, title="Монтаж", quantity=2, price=Decimal("120.50")),
                    OrderProductLink(id=42, order_id=10, proposal_id=32, title_snapshot="Модель Б", quantity=1, price=998, cost=139)])
        await db.commit()

    async def database():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = database
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "test-order-desk")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"Authorization": "Bearer test-order-desk"}) as client:
        yield client


def command(desk, **change):
    return {**ACTOR, "expected_revision": desk["revision"], "idempotency_key": str(uuid4()), "change": change}


async def test_quote_saved_prices_and_scope(orders):
    path = f"{BASE}/10"
    card = await orders.get(path, params=ACTOR)
    assert card.status_code == 200, card.text
    desk = card.json()
    assert "cost" not in card.text and desk["selected_proposal_id"] == 31
    params = {**ACTOR, "expected_revision": desk["revision"], "proposal_id": 31}
    text = (await orders.get(path + "/quote", params=params)).json()["text"]
    assert all(s in text for s in ("Настенный А", "810,00 BYN", "Монтаж", "1 861,00 BYN"))
    assert all(s not in text for s in ("Модель Б", "Внутренняя", "139", "margin"))
    for endpoint in (f"{BASE}/11", f"{BASE}/12", f"{BASE}/14", path + "/quote"):
        args = {**params, "proposal_id": 999} if endpoint.endswith("quote") else ACTOR
        assert (await orders.get(endpoint, params=args)).status_code == 404
    assert (await orders.get(path, params={"telegram_id": 501})).status_code == 422
    assert (await orders.get(path, params={**ACTOR, "expected_context_version": 99})).status_code == 409
    assert (await orders.get(path, params={**ACTOR, "telegram_id": 502})).status_code == 403
    assert (await orders.get(path, params=ACTOR, headers={"Authorization": "Bearer wrong"})).status_code == 401


async def test_demo_and_legacy_reads_have_no_side_effects(orders, db_engine):
    path = f"{BASE}/13"
    first = (await orders.get(path, params=ACTOR)).json()
    assert first["selected_proposal_id"] is None and first["followup"]["can_edit_details"]
    assert first == (await orders.get(path, params=ACTOR)).json()
    async with AsyncSession(db_engine) as db:
        assert not await db.scalar(select(OrderProposal.id).where(OrderProposal.order_id == 13))
        assert not await db.scalar(select(CommandAuditEvent.id))
        (await db.get(Tenant, 1)).demo_read_only = True
        await db.commit()
    demo = (await orders.get(path, params=ACTOR)).json()
    assert not demo["followup"]["can_edit_details"] and not demo["document_issuers"]
    assert all(not p["can_add_equipment"] for p in demo["proposals"])
    assert (await orders.post(path + "/commands", json=command(demo, kind="set_details", comment="test"))).status_code == 403


async def test_edit_retries_racing_managers_and_audit(orders, db_engine):
    path = f"{BASE}/10"
    desk = (await orders.get(path, params=ACTOR)).json()
    payload = command(desk, kind="update_proposal_line", proposal_id=31, line_kind="product", line_id=41, quantity=3)
    results = await asyncio.gather(*(orders.post(path + "/commands", json=payload) for _ in range(2)))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
    updated = results[0].json()
    assert updated["revision"] != desk["revision"] and updated["proposals"][0]["product_lines"][0]["quantity"] == 3
    stale = await orders.post(path + "/commands", json=command(desk, kind="set_details", comment="устарело"))
    assert stale.status_code == 409
    assert (await orders.get(path + "/quote", params={**ACTOR, "expected_revision": desk["revision"],
                                                     "proposal_id": 31})).status_code == 409
    assert (await orders.post(path + "/commands", json={**payload, "expected_revision": updated["revision"]})).status_code == 409
    edits = [command(updated, kind="set_details", comment=note) for note in ("Обсудили монтаж", "Перезвонить")]
    racing = await asyncio.gather(*(orders.post(path + "/commands", json=edit) for edit in edits))
    assert sorted(r.status_code for r in racing) == [200, 409], [r.text for r in racing]
    current = (await orders.get(path, params=ACTOR)).json()
    assert current["followup"]["comment"] in ("Обсудили монтаж", "Перезвонить")
    # Replay reads the latest authorized desk, without restoring the old comment.
    assert (await orders.post(path + "/commands", json=payload)).json() == current
    async with AsyncSession(db_engine) as db:
        assert (await db.scalar(select(func.count()).select_from(CommandAuditEvent))) == 2
        (await db.get(Order, 10)).storefront_id = 2
        await db.commit()
    assert (await orders.post(path + "/commands", json=payload)).status_code == 404


async def test_manager_edit_invalidates_order_revision(orders, db_engine):
    path = f"{BASE}/10"
    desk = (await orders.get(path, params=ACTOR)).json()
    async with AsyncSession(db_engine) as db:
        # Manager line commands can change a saved price without a workflow change.
        (await db.get(OrderProductLink, 41)).price = 996
        await db.commit()
    result = await orders.post(path + "/commands", json=command(desk, kind="assign_customer", customer_id=65))
    assert result.status_code == 409
    latest = (await orders.get(path, params=ACTOR)).json()
    denied = await orders.post(path + "/commands", json=command(latest, kind="assign_customer", customer_id=65))
    assert denied.status_code == 404, denied.text
