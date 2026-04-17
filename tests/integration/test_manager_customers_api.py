import pytest
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerBranch, CustomerType, Order, OrderStatus


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_customer_detail_contains_extended_requisites(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        name="ООО Тест Клиент",
        phone="+375291111111",
        email="corp@example.com",
        type=CustomerType.company,
        inn="123456789",
        kpp="000001",
        full_legal_name="ООО Тест Клиент",
        legal_address="Минск, ул. Ленина, 1",
        actual_address="Минск, ул. Ленина, 2",
        bank_name="Тест Банк",
        bic="TESTBY2X",
        iban="BY00TEST30120000000000000000",
        signer_position="Директор",
        signer_name="Иван Иванов",
        acting_basis="Устава",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEW_LEAD,
        delivery_address="Минск, ул. Орловская, 15",
        title="Тестовая сделка",
    )
    db.add(order)
    await db.commit()

    response = await async_client.get(f"/api/manager/customers/{customer.id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == customer.id
    assert payload["inn"] == "123456789"
    assert payload["kpp"] == "000001"
    assert payload["full_legal_name"] == "ООО Тест Клиент"
    assert payload["legal_address"] == "Минск, ул. Ленина, 1"
    assert payload["actual_address"] == "Минск, ул. Ленина, 2"
    assert payload["bank_name"] == "Тест Банк"
    assert payload["bic"] == "TESTBY2X"
    assert payload["iban"] == "BY00TEST30120000000000000000"
    assert payload["signer_position"] == "Директор"
    assert payload["signer_name"] == "Иван Иванов"
    assert payload["acting_basis"] == "Устава"
    assert payload["last_delivery_address"] == "Минск, ул. Орловская, 15"
    assert payload["order_count"] == 1


@pytest.mark.asyncio
async def test_manager_customer_patch_updates_requisites(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        name="ООО Старое имя",
        phone="+375291112233",
        email="old@example.com",
        type=CustomerType.company,
        inn="123456789",
        full_legal_name="ООО Старое имя",
        legal_address="Минск, ул. Старая, 1",
        bank_name="Старый банк",
        bic="BPSBBY2X",
        iban="BY88BPSB30121159280199330000",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    patch_resp = await async_client.patch(
        f"/api/manager/customers/{customer.id}",
        headers=headers,
        json={
            "name": "ООО Новое имя",
            "phone": "+375 (29) 222-33-44",
            "email": "new@example.com",
            "full_legal_name": "ООО Новое имя",
            "legal_address": "Минск, ул. Новая, 10",
            "bank_name": "Новый банк",
            "bic": "AKBBBY2X",
            "iban": "BY12AKBB30120000000000000000",
            "signer_position": "Директор",
            "signer_name": "Петр Петров",
            "acting_basis": "Устава",
        },
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["name"] == "ООО Новое имя"
    assert patched["phone"] == "+375 (29) 222-33-44"
    assert patched["email"] == "new@example.com"
    assert patched["full_legal_name"] == "ООО Новое имя"
    assert patched["legal_address"] == "Минск, ул. Новая, 10"
    assert patched["bank_name"] == "Новый банк"
    assert patched["bic"] == "AKBBBY2X"
    assert patched["iban"] == "BY12AKBB30120000000000000000"
    assert patched["signer_position"] == "Директор"
    assert patched["signer_name"] == "Петр Петров"
    assert patched["acting_basis"] == "Устава"


@pytest.mark.asyncio
async def test_manager_customer_patch_rejects_invalid_iban(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        name="Тест",
        phone="+375291112233",
        type=CustomerType.company,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    patch_resp = await async_client.patch(
        f"/api/manager/customers/{customer.id}",
        headers=headers,
        json={"iban": "INVALID"},
    )
    assert patch_resp.status_code == 422
    detail = patch_resp.json()["detail"]
    assert detail["error_code"] == "validation_error"
    assert "iban" in detail["field_errors"]


@pytest.mark.asyncio
async def test_manager_customer_branch_crud(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(
        name="Филиальный клиент",
        phone="+375291009900",
        type=CustomerType.company,
        inn="123456789",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    create_resp = await async_client.post(
        f"/api/manager/customers/{customer.id}/branches",
        headers=headers,
        json={
            "name": "Склад Минск",
            "delivery_address": "Минск, Притыцкого 1",
            "contact_name": "Олег",
            "contact_phone": "+375 (29) 100-99-00",
            "is_default": True,
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["customer_id"] == customer.id
    assert created["delivery_address"] == "Минск, Притыцкого 1"
    assert created["is_default"] is True
    branch_id = created["id"]

    list_resp = await async_client.get(f"/api/manager/customers/{customer.id}/branches", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == branch_id

    patch_resp = await async_client.patch(
        f"/api/manager/customers/{customer.id}/branches/{branch_id}",
        headers=headers,
        json={"delivery_address": "Минск, Победителей 100", "is_default": False},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["delivery_address"] == "Минск, Победителей 100"
    assert patched["is_default"] is False

    delete_resp = await async_client.delete(
        f"/api/manager/customers/{customer.id}/branches/{branch_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "Branch deleted"

    branch_after = await db.get(CustomerBranch, branch_id)
    assert branch_after is None


@pytest.mark.asyncio
async def test_manager_customer_delete_blocked_if_has_orders(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(name="Delete Blocked", phone="+375299001122", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD))
    await db.commit()

    resp = await async_client.delete(f"/api/manager/customers/{customer.id}", headers=headers)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error_code"] == "bad_request"
    assert detail["message"] == "Невозможно удалить клиента, так как у него есть связанные заказы."

    still_exists = await db.get(Customer, customer.id)
    assert still_exists is not None


@pytest.mark.asyncio
async def test_manager_customer_delete_success_without_orders(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(name="Delete OK", phone="+375299112233", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    resp = await async_client.delete(f"/api/manager/customers/{customer.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    result = await db.execute(select(Customer).where(Customer.id == customer.id))
    assert result.scalar_one_or_none() is None
