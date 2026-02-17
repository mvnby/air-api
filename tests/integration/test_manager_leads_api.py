from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerType, Lead  # noqa: F401 - ensure SQLModel metadata includes lead table


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
