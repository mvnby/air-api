import pytest
from datetime import datetime, timedelta
from sqlmodel import select

from core.config import settings
from models import (
    BankReceipt,
    Customer,
    CustomerBranch,
    CustomerContract,
    CustomerType,
    GlobalConfig,
    Installer,
    Order,
    OrderDocument,
    OrderInstaller,
    OrderProductLink,
    OrderServiceLink,
    OrderStatus,
    Payment,
    PaymentCurrency,
    Product,
    RepairComplaintPreset,
    Service,
    ServiceTariff,
)
from models.order import OrderWorkStage


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_orders_list_segment_filter(async_client, db):
    c1 = Customer(name="B2C", phone="+375291111111", type=CustomerType.individual)
    c2 = Customer(name="B2B", phone="+375292222222", type=CustomerType.individual, inn="123456789")
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    db.add(Order(customer_id=c1.id, status=OrderStatus.NEW_LEAD, total_amount=100))
    db.add(Order(customer_id=c2.id, status=OrderStatus.NEW_LEAD, total_amount=200))
    db.add(Order(customer_id=None, status=OrderStatus.NEW_LEAD, total_amount=50))
    await db.commit()

    headers = await _auth_headers(async_client)

    r_b2c = await async_client.get("/api/manager/orders?segment=b2c", headers=headers)
    assert r_b2c.status_code == 200
    b2c_items = r_b2c.json()["items"]
    assert any(item["customer"] is None for item in b2c_items)
    assert all((item["customer"] is None) or (item["customer"]["inn"] in (None, "")) for item in b2c_items)

    r_b2b = await async_client.get("/api/manager/orders?segment=b2b", headers=headers)
    assert r_b2b.status_code == 200
    b2b_items = r_b2b.json()["items"]
    assert len(b2b_items) == 1
    assert b2b_items[0]["customer"]["inn"] == "123456789"


@pytest.mark.asyncio
async def test_manager_orders_overdue_filter(async_client, db):
    customer = Customer(name="Overdue", phone="+375293333333", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            next_followup_date=datetime.now() - timedelta(days=1),
        )
    )
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            next_followup_date=datetime.now() + timedelta(days=1),
        )
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/orders?segment=b2c&overdue_only=true",
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1


@pytest.mark.asyncio
async def test_manager_order_detail_uses_snapshot_prices(async_client, db):
    customer = Customer(name="Snapshot", phone="+375294444444", type=CustomerType.individual)
    product = Product(title="Snapshot Product", slug="snapshot-product", price=5000, area=30)
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, delivery_address="Минск, объект 1")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(
        OrderProductLink(
            order_id=order.id,
            product_id=product.id,
            quantity=2,
            price=1200,
            cost=700,
            installation_price=0,
            is_installation_included=False,
        )
    )
    await db.commit()

    product.price = 9100
    db.add(product)
    await db.commit()

    # Expunge the order from the session's identity map so the endpoint's
    # selectinload creates a fresh instance with up-to-date product_links.
    db.expunge(order)

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/orders/{order.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["product_lines"][0]["price"] == 1200


@pytest.mark.asyncio
async def test_manager_order_patch_scalar_fields(async_client, db):
    customer = Customer(name="Patch", phone="+375295555555", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, is_paid=False)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "status": "negotiation",
        "comment": "updated from manager",
        "is_paid": True,
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "negotiation"
    assert data["comment"] == "updated from manager"
    assert data["is_paid"] is True


@pytest.mark.asyncio
async def test_manager_order_patch_repair_workflow_adds_diagnostic_and_meta(async_client, db):
    customer = Customer(name="Repair Workflow", phone="+375295555558", type=CustomerType.company)
    tariff = ServiceTariff(
        service_kind="repair",
        selector_label="Диагностика кондиционера на объекте",
        estimate_template="Диагностика кондиционера на объекте",
        category="diagnostic",
        power_range="",
        base_price=80,
        is_active=True,
        sort_order=1,
    )
    db.add(customer)
    db.add(tariff)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "workflow_type": "repair",
        "repair_meta": {
            "customer_complaint": "Не охлаждает",
            "equipment_serial_number": "SN-REPAIR-1",
        },
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["workflow_type"] == "repair"
    assert data["repair_meta"]["customer_complaint"] == "Не охлаждает"
    assert data["repair_meta"]["equipment_serial_number"] == "SN-REPAIR-1"
    assert any("Диагностика кондиционера" in line["service_title"] for line in data["service_lines"])


@pytest.mark.asyncio
async def test_manager_repair_complaint_presets_crud_and_duplicates(async_client, db):
    db.add(
        RepairComplaintPreset(
            complaint_group="cooling",
            customer_phrase="Не холодит",
            document_wording="Снижение эффективности охлаждения.",
            likely_diagnosis="Вероятна утечка хладагента.",
            is_favorite=True,
            sort_order=10,
        )
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    list_response = await async_client.get(
        "/api/manager/repair-complaints?q=холод&favorites_only=true",
        headers=headers,
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["customer_phrase"] == "Не холодит"

    create_payload = {
        "complaint_group": "water_drainage",
        "customer_phrase": "Капает вода",
        "document_wording": "Нарушение отвода конденсата.",
        "likely_diagnosis": "Засор дренажа.",
        "is_favorite": False,
        "sort_order": 20,
    }
    create_response = await async_client.post("/api/manager/repair-complaints", json=create_payload, headers=headers)
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["customer_phrase"] == "Капает вода"

    duplicate_response = await async_client.post("/api/manager/repair-complaints", json=create_payload, headers=headers)
    assert duplicate_response.status_code == 409

    update_response = await async_client.put(
        f"/api/manager/repair-complaints/{created['id']}",
        json={"is_favorite": True, "likely_diagnosis": "Засор или перегиб дренажной трубки."},
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["is_favorite"] is True
    assert updated["likely_diagnosis"] == "Засор или перегиб дренажной трубки."


@pytest.mark.asyncio
async def test_manager_order_patch_title_and_labels_search(async_client, db):
    customer = Customer(name="Patch Labels", phone="+375295555557", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "title": "  Монтаж магазина  ",
        "manager_labels": [" срочно ", "СРОЧНО", "ждём адрес"],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Монтаж магазина"
    assert data["manager_labels"] == ["срочно", "ждём адрес"]

    by_title = await async_client.get("/api/manager/orders?segment=b2c&search=магазина", headers=headers)
    assert by_title.status_code == 200
    assert [item["id"] for item in by_title.json()["items"]] == [order.id]

    by_label = await async_client.get("/api/manager/orders?segment=b2c&search=адрес", headers=headers)
    assert by_label.status_code == 200
    assert [item["id"] for item in by_label.json()["items"]] == [order.id]


@pytest.mark.asyncio
async def test_manager_order_execution_auto_approves_proposal(async_client, db):
    customer = Customer(name="Execution", phone="+375295555556", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        proposal_status="draft",
        total_amount=100,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"status": "execution", "proposal_status": "draft"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "execution"
    assert data["proposal_status"] == "approved"
    assert data["ready_for_execution"] is True


@pytest.mark.asyncio
async def test_manager_order_patch_customer_branch_validation(async_client, db):
    c1 = Customer(name="Branch C1", phone="+375295511111", type=CustomerType.individual)
    c2 = Customer(name="Branch C2", phone="+375295522222", type=CustomerType.individual)
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    branch_c1 = CustomerBranch(customer_id=c1.id, name="Точка C1", delivery_address="Минск, Ленина 1", is_default=True)
    branch_c2 = CustomerBranch(customer_id=c2.id, name="Точка C2", delivery_address="Минск, Ленина 2", is_default=True)
    db.add(branch_c1)
    db.add(branch_c2)
    await db.commit()
    await db.refresh(branch_c1)
    await db.refresh(branch_c2)

    order = Order(customer_id=c1.id, status=OrderStatus.NEW_LEAD, is_paid=False)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)

    ok_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"customer_branch_id": branch_c1.id},
        headers=headers,
    )
    assert ok_resp.status_code == 200
    ok_payload = ok_resp.json()
    assert ok_payload["customer_branch"]["id"] == branch_c1.id
    assert ok_payload["customer_branch"]["delivery_address"] == "Минск, Ленина 1"

    bad_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"customer_branch_id": branch_c2.id},
        headers=headers,
    )
    assert bad_resp.status_code == 400
    assert "does not belong" in str(bad_resp.json()["detail"]["message"]).lower()


@pytest.mark.asyncio
async def test_manager_order_contract_selection_and_act_guard(async_client, db, monkeypatch):
    customer = Customer(name="Contract Customer", phone="+375296001122", type=CustomerType.company, inn="123456789")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    contract = CustomerContract(
        customer_id=customer.id,
        number="ОД-2026-777",
        valid_from=datetime(2026, 1, 1),
        valid_until=datetime(2026, 12, 31),
        status="active",
        google_file_id="fake",
        google_edit_url="https://docs.google.com/document/d/fake/edit",
    )
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, delivery_address="Минск, объект 1")
    db.add(contract)
    db.add(order)
    await db.commit()
    await db.refresh(contract)
    await db.refresh(order)

    headers = await _auth_headers(async_client)

    blocked = await async_client.post(f"/api/manager/orders/{order.id}/documents/act", headers=headers)
    assert blocked.status_code == 400
    assert "выберите открытый договор" in blocked.json()["detail"]["message"].lower()

    patch_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        headers=headers,
        json={"customer_contract_id": contract.id},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["customer_contract_id"] == contract.id
    assert patched["customer_contract"]["number"] == "ОД-2026-777"

    captured_replacements = []

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {
                "file_id": f"fake-{len(captured_replacements) + 1}",
                "edit_url": f"https://docs.google.com/document/d/fake-{len(captured_replacements) + 1}/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            captured_replacements.append(dict(replacements))

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    one_time_contract_with_open_selected = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/contract",
        headers=headers,
        params={"contract_date": "2026-04-26T00:00:00"},
    )
    assert one_time_contract_with_open_selected.status_code == 200
    assert captured_replacements[-1]["{{contract_number}}"].startswith("Д-2026-")
    assert captured_replacements[-1]["{{contract_number}}"] != "ОД-2026-777"
    assert captured_replacements[-1]["{{contract_date}}"] == "26.04.2026"

    one_time_order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(one_time_order)
    await db.commit()
    await db.refresh(one_time_order)
    db.add(
        OrderDocument(
            order_id=one_time_order.id,
            doc_type="contract",
            number="Д-2026-999",
            google_file_id="one-time-contract",
            google_edit_url="https://docs.google.com/document/d/one-time-contract/edit",
        )
    )
    await db.commit()

    one_time_act = await async_client.post(f"/api/manager/orders/{one_time_order.id}/documents/act", headers=headers)
    assert one_time_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "1"

    first_act = await async_client.post(f"/api/manager/orders/{order.id}/documents/act", headers=headers)
    assert first_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "1"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "1"
    assert captured_replacements[-1]["{{object_address}}"] == "Минск, объект 1"

    second_order = Order(customer_id=customer.id, customer_contract_id=contract.id, status=OrderStatus.NEW_LEAD)
    db.add(second_order)
    await db.commit()
    await db.refresh(second_order)

    second_act = await async_client.post(f"/api/manager/orders/{second_order.id}/documents/act", headers=headers)
    assert second_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "2"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "2"


@pytest.mark.asyncio
async def test_manager_document_roles_from_template_contract_and_order_override(async_client, db, monkeypatch):
    headers = await _auth_headers(async_client)
    db.add(
        GlobalConfig(
            key="contract_templates",
            value='[{"id":"tpl-service","name":"Услуги","document_role_type":"executor_customer","is_open_contract":true},{"id":"tpl-old","name":"Старый"}]',
            description="Contract templates",
        )
    )
    customer = Customer(name="Role Customer", phone="+375296009988", type=CustomerType.company, inn="123456789")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    templates_resp = await async_client.get("/api/manager/docs/templates/contract", headers=headers)
    assert templates_resp.status_code == 200
    templates = templates_resp.json()["items"]
    assert next(item for item in templates if item["id"] == "tpl-service")["document_role_type"] == "executor_customer"
    assert next(item for item in templates if item["id"] == "tpl-service")["is_open_contract"] is True
    assert next(item for item in templates if item["id"] == "tpl-old")["document_role_type"] == "seller_buyer"
    assert next(item for item in templates if item["id"] == "tpl-old")["is_open_contract"] is False

    captured_replacements = []

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {
                "file_id": f"role-fake-{len(captured_replacements) + 1}",
                "edit_url": f"https://docs.google.com/document/d/role-fake-{len(captured_replacements) + 1}/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            captured_replacements.append(dict(replacements))

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    one_time_order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, delivery_address="Витебск, объект")
    db.add(one_time_order)
    await db.commit()
    await db.refresh(one_time_order)

    contract_resp = await async_client.post(
        f"/api/manager/orders/{one_time_order.id}/documents/contract",
        headers=headers,
        params={"template_id": "tpl-service", "contract_date": "2026-04-27T00:00:00"},
    )
    assert contract_resp.status_code == 200
    assert all("продавцом" not in replacements for replacements in captured_replacements)
    refreshed_order = await db.get(Order, one_time_order.id)
    assert refreshed_order.document_role_type == "executor_customer"

    act_resp = await async_client.post(f"/api/manager/orders/{one_time_order.id}/documents/act", headers=headers)
    assert act_resp.status_code == 200
    assert captured_replacements[-2]["{{object_address}}"] == "Витебск, объект"
    assert captured_replacements[-1]["продавцом"] == "исполнителем"
    assert captured_replacements[-1]["покупателя"] == "заказчика"

    contract = CustomerContract(
        customer_id=customer.id,
        number="ОД-2026-555",
        valid_from=datetime(2026, 1, 1),
        valid_until=datetime(2026, 12, 31),
        status="active",
        document_role_type="executor_customer",
        google_file_id="fake-contract",
        google_edit_url="https://docs.google.com/document/d/fake-contract/edit",
    )
    override_order = Order(
        customer_id=customer.id,
        customer_contract_id=None,
        status=OrderStatus.NEW_LEAD,
        document_role_type="contractor_customer",
    )
    db.add(contract)
    db.add(override_order)
    await db.commit()
    await db.refresh(contract)
    override_order.customer_contract_id = contract.id
    db.add(override_order)
    await db.commit()
    await db.refresh(override_order)

    invoice_resp = await async_client.post(f"/api/manager/orders/{override_order.id}/documents/invoice", headers=headers)
    assert invoice_resp.status_code == 200, invoice_resp.text
    assert captured_replacements[-1]["продавцом"] == "подрядчиком"

    offer_resp = await async_client.post(f"/api/manager/orders/{override_order.id}/documents/offer", headers=headers)
    assert offer_resp.status_code == 200
    assert "продавцом" not in captured_replacements[-1]


@pytest.mark.asyncio
async def test_manager_order_switch_customer_clears_incompatible_branch(async_client, db):
    c1 = Customer(name="Switch C1", phone="+375295533333", type=CustomerType.individual)
    c2 = Customer(name="Switch C2", phone="+375295544444", type=CustomerType.individual)
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    branch_c1 = CustomerBranch(customer_id=c1.id, name="Склад C1", delivery_address="Витебск, 1", is_default=True)
    db.add(branch_c1)
    await db.commit()
    await db.refresh(branch_c1)

    order = Order(customer_id=c1.id, customer_branch_id=branch_c1.id, status=OrderStatus.NEW_LEAD, is_paid=False)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"customer_id": c2.id},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["customer"]["id"] == c2.id
    assert payload["customer_branch"] is None


@pytest.mark.asyncio
async def test_manager_order_patch_lines_preserves_installers(async_client, db):
    customer = Customer(name="Lines", phone="+375296666666", type=CustomerType.individual)
    product = Product(title="P", slug="prod-p", price=3000, area=30)
    service = Service(title="S", slug="service-s", base_price=100)
    installer = Installer(name="Installer 1", is_active=True)
    db.add(customer)
    db.add(product)
    db.add(service)
    db.add(installer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)
    await db.refresh(installer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=3000, cost=2000))
    db.add(OrderServiceLink(order_id=order.id, service_id=service.id, title=service.title, quantity=1, price=100, cost=50))
    db.add(OrderInstaller(order_id=order.id, installer_id=installer.id, role="main", agreed_pay=100))
    await db.commit()

    headers = await _auth_headers(async_client)
    payload = {
        "products": [{"product_id": product.id, "quantity": 2, "price": 1500, "cost": 1000}],
        "services": [{"service_id": service.id, "title": "S2", "quantity": 1, "price": 200, "cost": 80}],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200

    await db.refresh(order, attribute_names=["installers"])
    assert len(order.installers) == 1


@pytest.mark.asyncio
async def test_manager_order_proposals_can_duplicate_edit_and_select(async_client, db):
    customer = Customer(name="Proposal Customer", phone="+375296666667", type=CustomerType.individual)
    p1 = Product(title="Proposal P1", slug="proposal-p1", price=1000, area=25)
    p2 = Product(title="Proposal P2", slug="proposal-p2", price=2000, area=35)
    db.add(customer)
    db.add(p1)
    db.add(p2)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(p1)
    await db.refresh(p2)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    first_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": p1.id, "quantity": 1, "price": 1000, "cost": 700}], "services": []},
        headers=headers,
    )
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert len(first_data["proposals"]) == 1
    default_proposal = first_data["proposals"][0]
    assert default_proposal["is_selected"] is True
    assert default_proposal["total_amount"] == 1000

    duplicate_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{default_proposal['id']}/duplicate",
        json={"name": "Вариант 2"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 200
    duplicate_data = duplicate_resp.json()
    second_proposal = next(item for item in duplicate_data["proposals"] if item["name"] == "Вариант 2")
    assert second_proposal["total_amount"] == 1000

    edit_second_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {"product_id": p2.id, "quantity": 1, "price": 2000, "cost": 1300, "proposal_id": second_proposal["id"]},
            ],
            "services": [],
        },
        headers=headers,
    )
    assert edit_second_resp.status_code == 200
    edit_second_data = edit_second_resp.json()
    updated_second = next(item for item in edit_second_data["proposals"] if item["id"] == second_proposal["id"])
    assert updated_second["total_amount"] == 2000
    assert edit_second_data["product_lines"][0]["product_id"] == p1.id

    select_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{second_proposal['id']}/select",
        headers=headers,
    )
    assert select_resp.status_code == 200
    selected_data = select_resp.json()
    assert selected_data["total_amount"] == 2000
    assert selected_data["margin"] == 700
    assert selected_data["product_lines"][0]["product_id"] == p2.id
    assert next(item for item in selected_data["proposals"] if item["id"] == second_proposal["id"])["is_selected"] is True

    list_resp = await async_client.get("/api/manager/orders?segment=b2c", headers=headers)
    assert list_resp.status_code == 200
    list_item = next(item for item in list_resp.json()["items"] if item["id"] == order.id)
    assert list_item["total_amount"] == 2000
    assert list_item["margin"] == 700


@pytest.mark.asyncio
async def test_manager_order_offer_generation_uses_requested_proposal_and_creates_each_time(async_client, db, monkeypatch):
    customer = Customer(name="Proposal Docs", phone="+375296666668", type=CustomerType.individual)
    p1 = Product(title="Proposal Doc P1", slug="proposal-doc-p1", price=1000, area=25)
    p2 = Product(title="Proposal Doc P2", slug="proposal-doc-p2", price=2000, area=35)
    db.add(customer)
    db.add(p1)
    db.add(p2)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(p1)
    await db.refresh(p2)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    first_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": p1.id, "quantity": 1, "price": 1000, "cost": 700}], "services": []},
        headers=headers,
    )
    assert first_resp.status_code == 200
    default_proposal = first_resp.json()["proposals"][0]

    duplicate_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{default_proposal['id']}/duplicate",
        json={"name": "Вариант 2"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 200
    second_proposal = next(item for item in duplicate_resp.json()["proposals"] if item["name"] == "Вариант 2")

    edit_second_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {"product_id": p2.id, "quantity": 1, "price": 2000, "cost": 1300, "proposal_id": second_proposal["id"]},
            ],
            "services": [],
        },
        headers=headers,
    )
    assert edit_second_resp.status_code == 200

    table_captures = []

    class _FakeGoogleService:
        creds = object()

        def copy_template(self, template_id, title):
            index = len(table_captures) + 1
            return {
                "file_id": f"proposal-doc-{index}",
                "edit_url": f"https://docs.google.com/document/d/proposal-doc-{index}/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            pass

        def _fill_table(self, docs_service, file_id, table_data, has_footer):
            table_captures.append(table_data)

    from services import document_service
    import googleapiclient.discovery

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: object())

    second_offer_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/offer",
        params={"proposal_id": second_proposal["id"]},
        headers=headers,
    )
    assert second_offer_resp.status_code == 200, second_offer_resp.text
    second_offer = second_offer_resp.json()
    assert second_offer["proposal_id"] == second_proposal["id"]
    assert table_captures[-1][0][1] == "Proposal Doc P2"
    assert table_captures[-1][-1][-1] == "2000.00"

    first_offer_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/offer",
        params={"proposal_id": default_proposal["id"]},
        headers=headers,
    )
    assert first_offer_resp.status_code == 200, first_offer_resp.text
    first_offer = first_offer_resp.json()
    assert first_offer["proposal_id"] == default_proposal["id"]
    assert first_offer["doc_id"] != second_offer["doc_id"]
    assert table_captures[-1][0][1] == "Proposal Doc P1"
    assert table_captures[-1][-1][-1] == "1000.00"


@pytest.mark.asyncio
async def test_manager_order_patch_validation_errors(async_client, db):
    customer = Customer(name="Validation", phone="+375299999999", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "products": [{"product_id": 1, "quantity": 0, "price": 100, "cost": 10}],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "bad_request"
    assert detail["message"] == "Product quantity must be > 0"


@pytest.mark.asyncio
async def test_manager_order_generate_document(async_client, db, monkeypatch):
    customer = Customer(name="Doc", phone="+375297777777", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    class _FakeDoc:
        id = 1
        doc_type = "contract"
        google_edit_url = "https://docs.google.com/fake"

    captured = {}

    async def _fake_create_or_get_document(
        session,
        order_id,
        doc_type,
        document_template_id=None,
        template_id=None,
        contract_date=None,
        proposal_id=None,
    ):
        _ = (session, order_id, doc_type, document_template_id, template_id, proposal_id)
        captured["contract_date"] = contract_date
        return _FakeDoc()

    from services import document_service

    monkeypatch.setattr(document_service.DocumentService, "create_or_get_document", _fake_create_or_get_document)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/contract?contract_date=2026-04-20T00:00:00",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["doc_type"] == "contract"
    assert data["edit_url"].startswith("https://docs.google.com")
    assert captured["contract_date"] == datetime(2026, 4, 20)


@pytest.mark.asyncio
async def test_manager_order_generate_defect_act_placeholders(async_client, db, monkeypatch):
    customer = Customer(name='ООО "Сервис"', phone="+375297777777", type=CustomerType.company)
    product = Product(title="Кондиционер BEKO BK 260 AK", slug="beko-bk-260-ak", price=1000)
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEW_LEAD,
        technical_meta={
            "equipment_serial_number": "SN-001",
            "equipment_inventory_number": "INV-777",
            "technical_condition": "Компрессор отключается по защите.",
            "technical_conclusion": "Компрессор подлежит замене.",
            "recommended_decision": "Вывести из эксплуатации.",
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
    await db.commit()

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            captured["template_id"] = template_id
            captured["title"] = title
            return {"file_id": "fake-defect-act", "edit_url": "https://docs.google.com/document/d/fake-defect-act/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["file_id"] = file_id
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/defect_act?contract_date=2026-05-14T00:00:00",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["doc_type"] == "defect_act"
    assert captured["template_id"] == "1-MjndKurd91Ag_s8Fqc0Hhm37YxMITtD59HJ1RN2O_s"
    replacements = captured["replacements"]
    assert replacements["{{defect_act_number}}"].startswith("ДА-2026-")
    assert replacements["{{defect_act_date_text}}"] == "14 мая 2026 г."
    assert replacements["{{client_name}}"] == 'ООО "Сервис"'
    assert replacements["{{equipment_name}}"] == "Кондиционер BEKO BK 260 AK"
    assert replacements["{{equipment_serial_number}}"] == "SN-001"
    assert replacements["{{equipment_inventory_number}}"] == "INV-777"
    assert replacements["{{technical_condition}}"] == "Компрессор отключается по защите."
    assert replacements["{{technical_conclusion}}"] == "Компрессор подлежит замене."
    assert replacements["{{recommended_decision}}"] == "Вывести из эксплуатации."


@pytest.mark.asyncio
async def test_manager_order_defect_act_prefers_official_complaint_for_technical_condition(async_client, db, monkeypatch):
    customer = Customer(name="ООО Мегахенд", phone="+375291111111", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEW_LEAD,
        technical_meta={
            "repair": {
                "customer_complaint": "Вообще не холодит",
                "complaint_official": "Отсутствие теплообмена в режиме охлаждения",
            },
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            captured["template_id"] = template_id
            captured["title"] = title
            return {"file_id": "fake-defect-act", "edit_url": "https://docs.google.com/document/d/fake-defect-act/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["file_id"] = file_id
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/defect_act?contract_date=2026-05-14T00:00:00",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    replacements = captured["replacements"]
    assert replacements["{{technical_condition}}"] == "Отсутствие теплообмена в режиме охлаждения"
    assert replacements["{{customer_complaint}}"] == "Вообще не холодит"
    assert replacements["{{complaint_official}}"] == "Отсутствие теплообмена в режиме охлаждения"


@pytest.mark.asyncio
async def test_manager_order_patch_customer_critical_requisites_requires_confirmation(async_client, db):
    customer = Customer(
        name="Critical Requisites",
        phone="+375299999999",
        type=CustomerType.company,
        inn="123456789",
        iban="BY12ALFA30120000000000000000",
        bic="ALFABY2X",
        bank_name="Альфа-Банк",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "customer_iban": "BY88ALFA30120000000000000000",
        "customer_bic": "ALFABY2Y",
        "customer_bank_name": "Новый Банк",
    }

    without_confirm = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert without_confirm.status_code == 400
    assert "requires confirmation" in str(without_confirm.json()["detail"]).lower()

    with_confirm = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={**payload, "confirm_critical_customer_changes": True},
        headers=headers,
    )
    assert with_confirm.status_code == 200
    data = with_confirm.json()
    assert data["customer"]["iban"] == payload["customer_iban"]
    assert data["customer"]["bic"] == payload["customer_bic"]
    assert data["customer"]["bank_name"] == payload["customer_bank_name"]


@pytest.mark.asyncio
async def test_manager_order_list_documents(async_client, db):
    customer = Customer(name="DocList", phone="+375298888888", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    from models import OrderDocument
    doc1 = OrderDocument(
        order_id=order.id, 
        doc_type="contract", 
        number="D-001", 
        google_file_id="fid1", 
        google_edit_url="http://edit1"
    )
    doc2 = OrderDocument(
        order_id=order.id, 
        doc_type="invoice", 
        number="I-001", 
        google_file_id="fid2", 
        google_edit_url="http://edit2"
    )
    db.add(doc1)
    db.add(doc2)
    await db.commit()
    
    headers = await _auth_headers(async_client)
    resp = await async_client.get(f"/api/manager/orders/{order.id}/documents", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert {i["doc_type"] for i in items} == {"contract", "invoice"}


@pytest.mark.asyncio
async def test_manager_doc_download_404(async_client, db):
    headers = await _auth_headers(async_client)
    resp = await async_client.get("/api/manager/docs/999999/download", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error_code"] == "document_not_found"


@pytest.mark.asyncio
async def test_manager_doc_delete_success(async_client, db, monkeypatch):
    customer = Customer(name="DocDel", phone="+375290000000", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    from models import OrderDocument
    doc = OrderDocument(
        order_id=order.id, 
        doc_type="act", 
        number="A-001", 
        google_file_id="fid_del", 
        google_edit_url="http://edit_del"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    doc_id = doc.id
    
    # Mock google service delete
    from services.google_service import get_google_service
    deleted_ids = []
    def _fake_delete_file(file_id):
        deleted_ids.append(file_id)
        
    monkeypatch.setattr(get_google_service(), "delete_file", _fake_delete_file)
    
    headers = await _auth_headers(async_client)
    resp = await async_client.delete(f"/api/manager/docs/{doc_id}", headers=headers)
    assert resp.status_code == 200
    
    # Verify DB
    from sqlmodel import select
    res = await db.execute(select(OrderDocument).where(OrderDocument.id == doc_id))
    assert res.scalar_one_or_none() is None
    
    # Verify Google Call
    assert "fid_del" in deleted_ids


@pytest.mark.asyncio
async def test_manager_order_delete_cascades_related_entities(async_client, db, monkeypatch):
    customer = Customer(name="Delete Order", phone="+375290001234", type=CustomerType.individual)
    product = Product(title="Delete Product", slug="delete-product", price=4000, area=35)
    service = Service(title="Delete Service", slug="delete-service", base_price=200)
    installer = Installer(name="Delete Installer", is_active=True)
    db.add(customer)
    db.add(product)
    db.add(service)
    db.add(installer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)
    await db.refresh(installer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, delivery_address="Минск")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=4000, cost=2500))
    db.add(OrderServiceLink(order_id=order.id, service_id=service.id, title=service.title, quantity=1, price=200, cost=80))
    db.add(OrderInstaller(order_id=order.id, installer_id=installer.id, role="main", agreed_pay=100))
    db.add(OrderWorkStage(order_id=order.id, name="Монтаж"))
    db.add(Payment(order_id=order.id, amount=500))
    db.add(
        OrderDocument(
            order_id=order.id,
            doc_type="contract",
            number="D-DELETE-1",
            google_file_id="google-file-delete-1",
            google_edit_url="https://docs.google.com/fake",
        )
    )
    await db.commit()

    from services.google_service import get_google_service

    deleted_ids = []

    def _fake_delete_file(file_id):
        deleted_ids.append(file_id)

    monkeypatch.setattr(get_google_service(), "delete_file", _fake_delete_file)

    headers = await _auth_headers(async_client)
    resp = await async_client.delete(f"/api/manager/orders/{order.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert await db.get(Order, order.id) is None

    plinks = await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))
    assert plinks.scalars().first() is None
    slinks = await db.execute(select(OrderServiceLink).where(OrderServiceLink.order_id == order.id))
    assert slinks.scalars().first() is None
    installers = await db.execute(select(OrderInstaller).where(OrderInstaller.order_id == order.id))
    assert installers.scalars().first() is None
    stages = await db.execute(select(OrderWorkStage).where(OrderWorkStage.order_id == order.id))
    assert stages.scalars().first() is None
    payments = await db.execute(select(Payment).where(Payment.order_id == order.id))
    assert payments.scalars().first() is None
    docs = await db.execute(select(OrderDocument).where(OrderDocument.order_id == order.id))
    assert docs.scalars().first() is None
    assert "google-file-delete-1" in deleted_ids


@pytest.mark.asyncio
async def test_manager_order_detail_includes_bank_receipt_payment_details(async_client, db):
    customer = Customer(name="Bank Customer", phone="+375290009999", type=CustomerType.individual, inn="192663084")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.EXECUTION, total_amount=420, balance_due=420)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    receipt = BankReceipt(
        status="matched",
        operation_type="incoming_funds",
        sender_email="bank-statement@local",
        subject="Bank statement CSV import",
        fingerprint="order-detail-bank-receipt",
        received_at=datetime(2026, 5, 22, 14, 57),
        amount=420,
        currency=PaymentCurrency.BYN,
        payer_name='ООО "МЕГАХЕНД"',
        payer_unp="192663084",
        payer_account="BY44PJCB30120493741000000933",
        payment_document_raw="17",
        payment_document_number="17",
        payment_purpose="ОПЛАТА СОГЛАСНО СЧЕТА 61",
        matched_order_id=order.id,
        raw_body="statement row",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    payment = Payment(order_id=order.id, bank_receipt_id=receipt.id, amount=420)
    db.add(payment)
    await db.commit()
    db.expunge(order)

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/orders/{order.id}", headers=headers)

    assert response.status_code == 200
    payments = response.json()["payments"]
    assert len(payments) == 1
    assert payments[0]["bank_receipt_id"] == receipt.id
    assert payments[0]["bank_receipt"]["payment_document_number"] == "17"
    assert payments[0]["bank_receipt"]["payer_unp"] == "192663084"
    assert payments[0]["bank_receipt"]["payment_purpose"] == "ОПЛАТА СОГЛАСНО СЧЕТА 61"
