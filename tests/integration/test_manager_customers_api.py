import pytest
from datetime import datetime, timedelta
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerBranch, CustomerContract, CustomerType, GlobalConfig, Order, OrderStatus


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
async def test_manager_customer_favorite_patch_and_sort(async_client, db):
    headers = await _auth_headers(async_client)

    regular_customer = Customer(
        name="ООО Обычный клиент",
        phone="+375291110000",
        type=CustomerType.company,
        created_at=datetime(2026, 1, 10, 10, 0, 0),
    )
    favorite_customer = Customer(
        name="ООО Частый клиент",
        phone="+375291110001",
        type=CustomerType.company,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    db.add(regular_customer)
    db.add(favorite_customer)
    await db.commit()
    await db.refresh(regular_customer)
    await db.refresh(favorite_customer)

    db.add(
        Order(
            customer_id=regular_customer.id,
            status=OrderStatus.NEW_LEAD,
            title="Обычная сделка",
        )
    )
    db.add(
        Order(
            customer_id=favorite_customer.id,
            status=OrderStatus.NEW_LEAD,
            title="Частая сделка",
        )
    )
    await db.commit()

    patch_resp = await async_client.patch(
        f"/api/manager/customers/{favorite_customer.id}",
        headers=headers,
        json={"is_favorite": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_favorite"] is True

    list_resp = await async_client.get(
        "/api/manager/customers?only_with_orders=true&limit=10",
        headers=headers,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert items[0]["id"] == favorite_customer.id
    assert items[0]["is_favorite"] is True


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
async def test_manager_customer_contract_create_and_dashboard_notice(async_client, db, monkeypatch):
    headers = await _auth_headers(async_client)
    captured = {}

    class FakeGoogleService:
        def copy_template(self, template_id, title):
            captured["template_id"] = template_id
            captured["title"] = title
            return {"file_id": "fake-file-id", "edit_url": "https://docs.google.com/document/d/fake-file-id/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["file_id"] = file_id
            captured["replacements"] = replacements

    monkeypatch.setattr("services.customer_contract_service.get_google_service", lambda: FakeGoogleService())

    customer = Customer(
        name="ООО Договор",
        phone="+375291223344",
        type=CustomerType.company,
        inn="123456789",
        full_legal_name="ООО Договор",
        legal_address="Минск, Победителей 1",
    )
    db.add(customer)
    db.add(
        GlobalConfig(
            key="contract_templates",
            value='[{"id":"service-template","name":"Сервис","document_role_type":"executor_customer","is_open_contract":true}]',
            description="Contract templates",
        )
    )
    await db.commit()
    await db.refresh(customer)

    create_resp = await async_client.post(
        f"/api/manager/customers/{customer.id}/contracts",
        headers=headers,
        json={
            "contract_date": "2026-01-15T00:00:00",
            "valid_until": "2027-01-15T00:00:00",
            "template_id": "service-template",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["number"].startswith("ОД-2026-")
    assert created["status"] == "active"
    assert created["edit_url"].endswith("/edit")
    assert captured["template_id"] == "service-template"
    assert captured["replacements"]["{{contract_valid_until}}"] == "15.01.2027"
    assert captured["replacements"]["{{contract_number}}"] == created["number"]
    assert created["document_role_type"] == "executor_customer"

    list_resp = await async_client.get(f"/api/manager/customers/{customer.id}/contracts", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["items"][0]["number"] == created["number"]

    contract = await db.get(CustomerContract, created["id"])
    contract.valid_until = datetime.now() + timedelta(days=7)
    db.add(contract)
    await db.commit()

    dashboard_resp = await async_client.get("/api/manager/dashboard/stats", headers=headers)
    assert dashboard_resp.status_code == 200
    notices = dashboard_resp.json()["expiring_contracts"]
    assert any(item["contract_id"] == created["id"] for item in notices)


@pytest.mark.asyncio
async def test_manager_customer_contract_upload_and_delete(async_client, db, monkeypatch):
    headers = await _auth_headers(async_client)
    captured = {"deleted": []}

    class FakeGoogleService:
        def upload_file(self, file_path, filename, mime_type, folder_id=None):
            captured["filename"] = filename
            captured["mime_type"] = mime_type
            captured["folder_id"] = folder_id
            with open(file_path, "rb") as fh:
                captured["content"] = fh.read()
            return "uploaded-contract-file"

        def delete_file(self, file_id):
            captured["deleted"].append(file_id)

    monkeypatch.setattr("services.customer_contract_service.get_google_service", lambda: FakeGoogleService())

    customer = Customer(
        name="ООО Загруженный",
        phone="+375291223355",
        type=CustomerType.company,
        inn="123456789",
    )
    db.add(customer)
    db.add(
        GlobalConfig(
            key="contract_templates",
            value='[{"id":"uploaded-template","name":"Загрузка","document_role_type":"executor_customer","is_open_contract":true}]',
            description="Contract templates",
        )
    )
    await db.commit()
    await db.refresh(customer)

    upload_resp = await async_client.post(
        f"/api/manager/customers/{customer.id}/contracts/upload",
        headers=headers,
        data={
            "number": "EXT-2026-001",
            "contract_date": "2026-02-10T00:00:00",
            "valid_until": "2027-02-10T00:00:00",
            "template_id": "uploaded-template",
        },
        files={"file": ("external-contract.pdf", b"%PDF-contract", "application/pdf")},
    )
    assert upload_resp.status_code == 200
    uploaded = upload_resp.json()
    assert uploaded["number"] == "EXT-2026-001"
    assert uploaded["status"] == "active"
    assert uploaded["template_id"] == "uploaded-template"
    assert uploaded["document_role_type"] == "executor_customer"
    assert uploaded["edit_url"].endswith("/view?usp=sharing")
    assert "EXT-2026-001" in captured["filename"]
    assert captured["mime_type"] == "application/pdf"
    assert captured["content"] == b"%PDF-contract"

    linked_order = Order(
        customer_id=customer.id,
        customer_contract_id=uploaded["id"],
        status=OrderStatus.NEW_LEAD,
    )
    db.add(linked_order)
    await db.commit()
    await db.refresh(linked_order)

    delete_resp = await async_client.delete(
        f"/api/manager/customers/{customer.id}/contracts/{uploaded['id']}",
        headers=headers,
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "Contract deleted"
    assert captured["deleted"] == ["uploaded-contract-file"]
    assert await db.get(CustomerContract, uploaded["id"]) is None

    await db.refresh(linked_order)
    assert linked_order.customer_contract_id is None


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
