import pytest

from core.config import settings
from models import Customer, CustomerType, Order, OrderStatus


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
