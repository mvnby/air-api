from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from models import Customer, Lead, Order, OrderStatus, StaffUser, Storefront, Tenant, TenantMembership
from models.leads_inbox import InboxReadState
from models.personal_task import PersonalTask
from routers.internal_bot_workspace import router


BASE = "/api/internal/bot/v1/workspace/"
MANAGER = {"telegram_id": 501, "expected_context_version": 0}


@pytest.fixture
async def crm(db, monkeypatch):
    db.add_all([
        Tenant(id=2, slug="other", display_name="Другой"),
        StaffUser(id=11, telegram_id=501, username="crm-owner", display_name="Мария", primary_role="owner"),
        StaffUser(id=12, telegram_id=502, username="colleague", display_name="Коллега", primary_role="manager"),
        StaffUser(id=13, telegram_id=503, username="installer", display_name="Монтажник", primary_role="owner"),
    ])
    await db.flush()
    db.add_all([
        TenantMembership(tenant_id=1, staff_user_id=11, role="owner"),
        TenantMembership(tenant_id=1, staff_user_id=12, role="manager"),
        TenantMembership(tenant_id=1, staff_user_id=13, role="installer"),
        Storefront(id=2, tenant_id=1, slug="second", display_name="Другая витрина"),
        Storefront(id=3, tenant_id=2, slug="other", display_name="Другая компания"),
        Customer(id=21, tenant_id=1, name="Needle клиент", phone="+375291234567"),
        Customer(id=22, tenant_id=2, name="Needle секрет", phone="+375291111111"),
    ])
    await db.flush()
    db.add_all([
        Order(id=31, tenant_id=1, storefront_id=1, customer_id=21, status=OrderStatus.NEGOTIATION,
              title="Needle монтаж", delivery_address="Адрес 7", total_amount=99999),
        Order(id=32, tenant_id=1, storefront_id=2, customer_id=21, status=OrderStatus.NEGOTIATION, title="Needle другая витрина"),
        Order(id=33, tenant_id=2, storefront_id=3, customer_id=22, status=OrderStatus.NEGOTIATION, title="Needle чужая фирма"),
        Order(id=51, tenant_id=1, storefront_id=1, title="Needle запрос", comment="Исходное описание", lead_source="email"),
        Lead(id=51, tenant_id=1, storefront_id=1, request_text="Needle диагностика", name="Приёмная", source="site"),
        Lead(id=52, tenant_id=1, storefront_id=2, request_text="Needle скрытая витрина"),
        Lead(id=53, tenant_id=2, storefront_id=3, request_text="Needle чужая фирма"),
        PersonalTask(id=61, tenant_id=1, storefront_id=1, author_staff_user_id=12, assignee_staff_user_id=11,
                     text="Позвонить", description="Needle 50% подтверждено"),
        PersonalTask(id=62, tenant_id=1, storefront_id=1, author_staff_user_id=11, assignee_staff_user_id=12, text="Needle счёт"),
        PersonalTask(id=63, tenant_id=1, storefront_id=1, author_staff_user_id=12, assignee_staff_user_id=12, text="Needle секрет"),
        PersonalTask(id=64, tenant_id=1, storefront_id=2, author_staff_user_id=11, assignee_staff_user_id=11, text="Needle витрина"),
        PersonalTask(id=65, tenant_id=1, storefront_id=1, author_staff_user_id=11, assignee_staff_user_id=11,
                     text="Needle архив", status="completed"),
    ])
    await db.commit()

    async def database():
        async with AsyncSession(db.bind, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = database
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "crm-test-only")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local",
                           headers={"Authorization": "Bearer crm-test-only"}) as client:
        yield client


async def test_manager_scope_bounds_search_and_detail(crm):
    for section, ids in (("customers", {21}), ("orders", {31}), ("incoming", {51}), ("tasks", {61, 62})):
        first = await crm.get(BASE + section, params={**MANAGER, "q": "Needle", "limit": 1})
        assert first.status_code == 200, first.text
        data = first.json()
        total = 2 if section in ("incoming", "tasks") else 1
        assert data["total"] == total and data["items"][0]["id"] in ids
        last = await crm.get(BASE + section, params={**MANAGER, "q": "Needle", "limit": 1, "page": total + 1})
        assert last.json()["items"] == []
    result = await crm.get(BASE + "tasks", params={**MANAGER, "q": "50%"})
    assert [row["id"] for row in result.json()["items"]] == [61]
    for path in ("customers/22", "orders/32", "orders/33", "tasks/63", "tasks/64",
                 "incoming/52?kind=lead", "incoming/53?kind=lead"):
        response = await crm.get(BASE + path, params={**MANAGER, **({"kind": "lead"} if "incoming" in path else {})})
        assert response.status_code == 404, (path, response.text)
    order = (await crm.get(BASE + "orders/31", params=MANAGER)).json()
    assert order["customer_id"] == 21 and order["manager_url"].endswith("/orders/31?company=1&site=main")
    assert ("Сумма", "0,00 BYN") in [(fact["label"], fact["value"]) for fact in order["facts"]]
    assert all("99999" not in fact["value"] for fact in order["facts"])
    assert (await crm.get(BASE + "tasks", params={**MANAGER, "limit": 41})).status_code == 422
    assert (await crm.get(BASE + "tasks", params={**MANAGER, "filter": "history"})).status_code == 422
    assert (await crm.get(BASE + "incoming/51", params=MANAGER)).status_code == 422


async def test_workspace_proof_role_version_and_demo(crm, db):
    assert (await crm.get(BASE + "tasks", params={"telegram_id": 501})).status_code == 422
    assert (await crm.get(BASE + "tasks", params=MANAGER, headers={"Authorization": "Bearer invalid"})).status_code == 401
    assert (await crm.get(BASE + "tasks", params={**MANAGER, "telegram_id": 503})).status_code == 403
    assert (await crm.get(BASE + "orders", params={**MANAGER, "expected_context_version": 1})).status_code == 409
    user = await db.get(StaffUser, 11)
    user.must_change_password = True
    await db.commit()
    assert (await crm.get(BASE + "tasks", params=MANAGER)).status_code == 403
    user.must_change_password = False
    tenant = await db.get(Tenant, 1)
    tenant.demo_read_only = True
    await db.commit()
    assert (await crm.get(BASE + "customers/21", params=MANAGER)).json()["actions"] == []
    assert (await crm.post(BASE + "customers/21/draft", json=MANAGER)).status_code == 403


async def test_personal_task_retry_is_scoped_to_author_or_assignee(crm, db):
    command = {**MANAGER, "expected_version": 1, "action": "complete", "idempotency_key": "task-complete-0001"}
    path = BASE + "tasks/61/status"
    result = await crm.post(path, json=command)
    assert result.status_code == 200, result.text
    assert result.json()["actions"] == ["reopen"] and result.json()["version"] == 2
    assert (await crm.post(path, json=command)).json()["version"] == 2
    assert (await crm.post(path, json={**command, "idempotency_key": "task-complete-0002"})).status_code == 409
    assert (await crm.post(BASE + "tasks/63/status", json=command)).status_code == 404
    result = await crm.post(path, json={**command, "action": "reopen", "expected_version": 2, "idempotency_key": "task-reopen-000001"})
    assert result.json()["actions"] == ["complete"] and result.json()["version"] == 3
    task = await db.get(PersonalTask, 61, populate_existing=True)
    task.assignee_staff_user_id = 12
    await db.commit()
    assert (await crm.post(path, json=command)).status_code == 404


async def test_inbox_uses_actor_username_and_entity_kind(crm, db):
    path = BASE + "incoming/51"
    items = (await crm.get(BASE + "incoming", params=MANAGER)).json()["items"]
    assert {(i["kind"], i["id"]) for i in items} == {("lead", 51), ("order", 51)}
    result = await crm.post(path + "/read", json={**MANAGER, "kind": "lead", "is_read": True})
    assert result.status_code == 200, result.text
    assert result.json()["item"]["is_read"]
    assert not (await crm.get(path, params={**MANAGER, "kind": "order"})).json()["item"]["is_read"]
    assert not (await crm.get(path, params={**MANAGER, "telegram_id": 502, "kind": "lead"})).json()["item"]["is_read"]
    assert (await db.execute(select(InboxReadState.username))).scalar_one() == "crm-owner"


@pytest.mark.parametrize("kind", ["lead", "order"])
async def test_incoming_qualification_preserves_source_and_idempotency(crm, db, kind):
    card = (await crm.get(BASE + "incoming/51", params={**MANAGER, "kind": kind})).json()
    payload = {**MANAGER, "kind": kind, "expected_version": card["version"], "customer_id": 21,
               "workflow_type": "repair", "idempotency_key": "crm-qualification-0001"}
    path = BASE + "incoming/51/service-order"
    assert (await crm.post(path, json={**payload, "customer_id": 22})).status_code == 404
    stale = await crm.post(path, json={**payload, "expected_version": card["version"] + 1})
    assert stale.status_code == 409, stale.text
    before = await db.scalar(select(func.count()).select_from(Order))
    first = await crm.post(path, json=payload)
    assert first.status_code == 200, first.text
    replay = await crm.post(path, json=payload)
    assert replay.status_code == 200 and replay.json() == first.json(), replay.text
    order = await db.get(Order, first.json()["order_id"], populate_existing=True)
    assert order.status == "negotiation" and order.customer_id == 21
    if kind == "lead":
        lead = await db.get(Lead, 51, populate_existing=True)
        assert lead.converted_order_id == order.id and lead.request_text in order.comment
    else:
        assert order.id == 51 and order.comment == "Исходное описание"
    assert await db.scalar(select(func.count()).select_from(Order)) == before + (1 if kind == "lead" else 0)


async def test_customer_bound_draft(crm):
    denied = await crm.post(BASE + "customers/22/draft", json=MANAGER)
    assert denied.status_code == 404
    draft = await crm.post(BASE + "customers/21/draft", json=MANAGER)
    assert draft.status_code == 200, draft.text
    assert draft.json()["draft"]["customer_id"] == 21 and draft.json()["status"] == "active"
