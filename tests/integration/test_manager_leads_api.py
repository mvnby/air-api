from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerBranch, CustomerType, Lead, Order  # noqa: F401 - ensure SQLModel metadata includes lead table


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_leads_crud_flow(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "phone",
            "name": "Новый лид",
            "phone": "+375291111111",
            "request_text": "Нужна консультация по компрессору",
            "next_followup_date": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["status"] == "new"
    assert created["segment_hint"] == "unknown"

    list_resp = await async_client.get("/api/manager/leads", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == created["id"] for item in list_resp.json()["items"])

    patch_resp = await async_client.patch(
        f"/api/manager/leads/{created['id']}",
        headers=headers,
        json={"status": "contacted", "next_followup_date": (datetime.now() + timedelta(days=1)).isoformat()},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["status"] == "contacted"


@pytest.mark.asyncio
async def test_manager_leads_overdue_filter(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Overdue Lead",
            "request_text": "Перезвонить",
            "next_followup_date": (datetime.now() - timedelta(days=1)).isoformat(),
        },
    )
    assert create_resp.status_code == 200

    response = await async_client.get("/api/manager/leads?overdue_only=true", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["name"] == "Overdue Lead" for item in items)


@pytest.mark.asyncio
async def test_manager_lead_qualify_creates_order(async_client, db):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "email",
            "name": "ООО Клиент",
            "email": "lead@example.com",
            "inn": "123456789",
            "request_text": "Нужен подбор оборудования",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "full_legal_name": "ООО Клиент",
            "legal_address": "Минск, ул. Ленина, 1",
            "iban": "BY13ALFA30122644440010270000",
            "bic": "ALFABY2X",
            "bank_name": "ЗАО Альфа-Банк, Минск",
            "delivery_address": "Минск",
            "order_comment": "Сформирована сделка",
        },
    )
    assert qualify_resp.status_code == 200
    qualified = qualify_resp.json()
    assert qualified["lead"]["status"] == "qualified"
    assert qualified["order_id"] > 0
    assert qualified["customer_id"] > 0

    customer_result = await db.execute(select(Customer).where(Customer.id == qualified["customer_id"]))
    customer = customer_result.scalar_one()
    assert customer.legal_address == "Минск, ул. Ленина, 1"
    assert customer.iban == "BY13ALFA30122644440010270000"
    assert customer.bic == "ALFABY2X"
    assert customer.bank_name == "ЗАО Альфа-Банк, Минск"

    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    order = (
        await db.execute(select(Order).where(Order.id == qualified["order_id"]))
    ).scalar_one()
    assert (lead.tenant_id, lead.storefront_id) == (1, 1)
    assert (order.tenant_id, order.storefront_id) == (
        lead.tenant_id,
        lead.storefront_id,
    )


@pytest.mark.asyncio
async def test_manager_lead_mark_lost_hidden_from_default_list(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "phone",
            "name": "Lost Lead",
            "phone": "+375292222222",
            "request_text": "Нет подходящего товара",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    lost_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/mark-lost",
        headers=headers,
        json={"status": "lost", "loss_reason": "no_product"},
    )
    assert lost_resp.status_code == 200
    assert lost_resp.json()["status"] == "lost"

    default_list = await async_client.get("/api/manager/leads", headers=headers)
    assert default_list.status_code == 200
    assert all(item["id"] != lead_id for item in default_list.json()["items"])

    lost_list = await async_client.get("/api/manager/leads?status=lost", headers=headers)
    assert lost_list.status_code == 200
    assert any(item["id"] == lead_id for item in lost_list.json()["items"])


@pytest.mark.asyncio
async def test_manager_lead_qualify_reuses_customer_and_keeps_existing_requisites(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        tenant_id=1,
        name="ООО Эвистор",
        phone="+375331112233",
        email="info@evistor.by",
        type=CustomerType.company,
        inn="300149331",
        full_legal_name="ОАО «Завод «ЭВИСТОР»",
        legal_address="210101, г. Витебск, проспект Фрунзе, 81",
        bank_name="ОАО «БПС-Сбербанк», г. Витебск",
        bic="BPSBBY2X",
        iban="BY88BPSB30121159280199330000",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Повторный клиент",
            "email": "info@evistor.by",
            "inn": "300149331",
            "request_text": "Новый запрос",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "name": "ОАО «Завод «ЭВИСТОР»",
            "full_legal_name": "ОАО «Завод «ЭВИСТОР»",
        },
    )
    assert qualify_resp.status_code == 200
    data = qualify_resp.json()
    assert data["customer_id"] == customer.id

    await db.refresh(customer)
    assert customer.bank_name == "ОАО «БПС-Сбербанк», г. Витебск"
    assert customer.bic == "BPSBBY2X"
    assert customer.iban == "BY88BPSB30121159280199330000"


@pytest.mark.asyncio
async def test_manager_lead_qualify_prefers_more_complete_customer_on_equal_match(async_client, db):
    headers = await _auth_headers(async_client)

    sparse = Customer(
        tenant_id=1,
        name="Client Sparse",
        phone="+375291234567",
        email="duplicate@example.com",
        type=CustomerType.company,
        inn="391398328",
        full_legal_name="ООО Спарс",
    )
    rich = Customer(
        tenant_id=1,
        name="Client Rich",
        phone="+375291234567",
        email="duplicate@example.com",
        type=CustomerType.company,
        inn="391398328",
        full_legal_name="ООО Рич",
        legal_address="Минск, ул. Ленина, 1",
        bank_name="ЗАО Альфа-Банк",
        bic="ALFABY2X",
        iban="BY13ALFA30122644440010270000",
    )
    db.add(sparse)
    db.add(rich)
    await db.commit()
    await db.refresh(sparse)
    await db.refresh(rich)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Match Priority",
            "email": "duplicate@example.com",
            "inn": "391398328",
            "request_text": "Проверка приоритета дедупа",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={"name": "Match Priority"},
    )
    assert qualify_resp.status_code == 200
    payload = qualify_resp.json()
    assert payload["customer_id"] == rich.id


@pytest.mark.asyncio
async def test_manager_lead_qualify_with_selected_customer_id_reuses_exact_customer(async_client, db):
    headers = await _auth_headers(async_client)

    target = Customer(
        tenant_id=1,
        name="Target Customer",
        phone="+375291111111",
        email="target@example.com",
        type=CustomerType.company,
        inn="123456789",
        full_legal_name="ООО Таргет",
        bank_name="Target Bank",
        bic="AKBBBY2X",
        iban="BY12AKBB30120000000000000000",
    )
    other = Customer(
        tenant_id=1,
        name="Other Customer",
        phone="+375292222222",
        email="other@example.com",
        type=CustomerType.company,
        inn="987654321",
        full_legal_name="ООО Другой",
    )
    db.add(target)
    db.add(other)
    await db.commit()
    await db.refresh(target)
    await db.refresh(other)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Selected customer flow",
            "request_text": "Проверка выбранного клиента",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "customer_id": target.id,
            "name": "Target Customer",
            "inn": "391398328",
        },
    )
    assert qualify_resp.status_code == 200
    payload = qualify_resp.json()
    assert payload["customer_id"] == target.id

    await db.refresh(target)
    assert target.bank_name == "Target Bank"
    assert target.bic == "AKBBBY2X"
    assert target.iban == "BY12AKBB30120000000000000000"


@pytest.mark.asyncio
async def test_manager_lead_qualify_with_selected_branch_sets_order_snapshot(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        tenant_id=1,
        name="Branch Customer",
        phone="+375299998877",
        type=CustomerType.company,
        inn="444444444",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    branch = CustomerBranch(
        customer_id=customer.id,
        name="Склад Витебск",
        delivery_address="Витебск, Ленина 10",
        is_default=True,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Lead with selected branch",
            "request_text": "Привязка к филиалу",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "customer_id": customer.id,
            "customer_branch_id": branch.id,
            "order_comment": "Использовать адрес филиала",
        },
    )
    assert qualify_resp.status_code == 200
    payload = qualify_resp.json()
    assert payload["customer_id"] == customer.id

    order = await db.get(Order, payload["order_id"])
    assert order is not None
    assert order.customer_branch_id == branch.id
    assert order.delivery_address == "Витебск, Ленина 10"


@pytest.mark.asyncio
async def test_manager_lead_qualify_rejects_branch_of_other_customer(async_client, db):
    headers = await _auth_headers(async_client)

    customer_a = Customer(tenant_id=1, name="Company A", phone="+375291010101", type=CustomerType.company, inn="555555555")
    customer_b = Customer(tenant_id=1, name="Company B", phone="+375292020202", type=CustomerType.company, inn="666666666")
    db.add(customer_a)
    db.add(customer_b)
    await db.commit()
    await db.refresh(customer_a)
    await db.refresh(customer_b)

    branch_b = CustomerBranch(
        customer_id=customer_b.id,
        name="Филиал B",
        delivery_address="Минск, Победителей 5",
        is_default=True,
    )
    db.add(branch_b)
    await db.commit()
    await db.refresh(branch_b)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Lead invalid selected branch",
            "request_text": "Проверка mismatch",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "customer_id": customer_a.id,
            "customer_branch_id": branch_b.id,
        },
    )
    assert qualify_resp.status_code == 400
    assert "does not belong" in str(qualify_resp.json()["detail"]["message"]).lower()


@pytest.mark.asyncio
async def test_manager_lead_qualify_handoff_smoke_open_order_and_customer(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Handoff Smoke",
            "email": "handoff-smoke@example.com",
            "request_text": "Проверка handoff",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "name": "Handoff Smoke",
            "email": "handoff-smoke@example.com",
            "order_comment": "Smoke handoff",
        },
    )
    assert qualify_resp.status_code == 200
    qualified = qualify_resp.json()
    order_id = qualified["order_id"]
    customer_id = qualified["customer_id"]

    order_detail_resp = await async_client.get(f"/api/manager/orders/{order_id}", headers=headers)
    assert order_detail_resp.status_code == 200
    order_detail = order_detail_resp.json()
    assert order_detail["id"] == order_id
    assert order_detail["customer"]["id"] == customer_id

    customer_detail_resp = await async_client.get(f"/api/manager/customers/{customer_id}", headers=headers)
    assert customer_detail_resp.status_code == 200
    customer_detail = customer_detail_resp.json()
    assert customer_detail["id"] == customer_id
    assert customer_detail["order_count"] >= 1


@pytest.mark.asyncio
async def test_manager_lead_to_order_patch_smoke(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Lead Order Patch Smoke",
            "phone": "+375291234567",
            "request_text": "Smoke chain",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "name": "Lead Order Patch Smoke",
            "order_comment": "Created from lead",
        },
    )
    assert qualify_resp.status_code == 200
    order_id = qualify_resp.json()["order_id"]

    patch_resp = await async_client.patch(
        f"/api/manager/orders/{order_id}",
        headers=headers,
        json={
            "status": "negotiation",
            "comment": "Updated in smoke",
        },
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["id"] == order_id
    assert patched["status"] == "negotiation"


@pytest.mark.asyncio
async def test_manager_leads_reject_invalid_email_and_unp(async_client):
    headers = await _auth_headers(async_client)

    bad_email = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Bad Email",
            "email": "bad-email",
            "request_text": "test",
        },
    )
    assert bad_email.status_code == 422
    bad_email_detail = bad_email.json()["detail"]
    assert bad_email_detail["error_code"] == "validation_error"
    assert "email" in bad_email_detail["field_errors"]

    bad_unp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Bad UNP",
            "inn": "12345",
            "request_text": "test",
        },
    )
    assert bad_unp.status_code == 422
    bad_unp_detail = bad_unp.json()["detail"]
    assert bad_unp_detail["error_code"] == "validation_error"
    assert "inn" in bad_unp_detail["field_errors"]


@pytest.mark.asyncio
async def test_manager_qualify_rejects_invalid_iban(async_client):
    headers = await _auth_headers(async_client)
    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "IBAN Lead",
            "phone": "+375291234567",
            "request_text": "test",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "name": "IBAN Lead",
            "iban": "DE89370400440532013000",
        },
    )
    assert qualify_resp.status_code == 422
    detail = qualify_resp.json()["detail"]
    assert detail["error_code"] == "validation_error"
    assert "iban" in detail["field_errors"]
