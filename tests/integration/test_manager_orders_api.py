import json
import pytest
from io import BytesIO
from datetime import datetime, timedelta
from sqlmodel import select

from core.config import settings
from models import (
    BankReceipt,
    Customer,
    CustomerBranch,
    CustomerContract,
    CustomerType,
    DocumentTemplate,
    GlobalConfig,
    Installer,
    Order,
    OrderDocument,
    OrderInstaller,
    OrderProductLink,
    OrderServiceLink,
    OrderStageStatus,
    OrderStatus,
    Payment,
    PaymentCurrency,
    Product,
    RepairComplaintPreset,
    Service,
    ServiceTariff,
    Supplier,
    SupplyRequest,
    SupplyRequestLine,
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

    db.add(Order(customer_id=c1.id, status=OrderStatus.NEGOTIATION, total_amount=100))
    db.add(Order(customer_id=c2.id, status=OrderStatus.NEGOTIATION, total_amount=200))
    db.add(Order(customer_id=None, status=OrderStatus.NEGOTIATION, total_amount=50))
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

    r_all = await async_client.get("/api/manager/orders?segment=all", headers=headers)
    assert r_all.status_code == 200
    all_items = r_all.json()["items"]
    assert len(all_items) == 3
    assert any(item["customer"] is None for item in all_items)


@pytest.mark.asyncio
async def test_manager_orders_list_excludes_leads_before_pagination(async_client, db):
    customer = Customer(name="Real Order", phone="+375291010101", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    now = datetime.now()
    for idx in range(101):
        db.add(
            Order(
                customer_id=customer.id,
                status=OrderStatus.NEW_LEAD,
                created_at=now + timedelta(minutes=idx),
            )
        )
    real_order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        created_at=now - timedelta(days=1),
        title="Real visible order",
    )
    db.add(real_order)
    await db.commit()
    await db.refresh(real_order)

    headers = await _auth_headers(async_client)
    response = await async_client.get("/api/manager/orders?segment=b2c&limit=100", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert [item["id"] for item in payload["items"]] == [real_order.id]


@pytest.mark.asyncio
async def test_manager_orders_overdue_filter(async_client, db):
    customer = Customer(name="Overdue", phone="+375293333333", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEGOTIATION,
            next_followup_date=datetime.now() - timedelta(days=1),
        )
    )
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEGOTIATION,
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
    product = Product(title="Snapshot Product", slug="snapshot-product", price=5000, specs={"area_m2": 30})
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
        "negotiation_status": "awaiting_visit",
        "comment": "updated from manager",
        "is_paid": True,
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "negotiation"
    assert data["negotiation_status"] == "awaiting_visit"
    assert data["negotiation_status_changed_at"] is not None
    assert data["status_changed_at"] is not None
    assert data["comment"] == "updated from manager"
    assert data["is_paid"] is True


@pytest.mark.asyncio
async def test_manager_order_patch_closes_lost_without_deleting_order(async_client, db):
    customer = Customer(name="Lost Customer", phone="+375295555556", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION, total_amount=500, balance_due=500)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"status": "closed", "closing_result": "lost", "reject_reason": "Не сошлись по цене"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "closed"
    assert data["closing_result"] == "lost"
    assert data["reject_reason"] == "Не сошлись по цене"

    detail_response = await async_client.get(f"/api/manager/orders/{order.id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == order.id


@pytest.mark.asyncio
async def test_manager_order_patch_moves_to_execution_without_payment_flag(async_client, db):
    customer = Customer(name="Trusted Customer", phone="+375295555557", type=CustomerType.individual)
    product = Product(title="Trusted AC", slug="trusted-ac", price=1000, specs={"area_m2": 20})
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION, total_amount=0, balance_due=0)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "status": "execution",
            "execution_status": "order_equipment",
            "execution_without_payment": True,
            "execution_without_payment_reason": "Постоянный клиент",
            "products": [{"product_id": product.id, "quantity": 1, "price": 1000, "cost": 700}],
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "execution"
    assert data["proposal_status"] == "approved"
    assert data["execution_status"] == "order_equipment"
    assert data["execution_status_changed_at"] is not None
    assert data["execution_without_payment"] is True
    assert data["execution_without_payment_reason"] == "Постоянный клиент"


@pytest.mark.asyncio
async def test_manager_order_patch_recomputes_balance_before_closing_won(async_client, db):
    customer = Customer(name="Close Guard", phone="+375295555551", type=CustomerType.individual)
    product = Product(title="Close Guard Product", slug="close-guard-product", price=500, specs={"area_m2": 20})
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION, total_amount=0, balance_due=0)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "status": "closed",
            "closing_result": "won",
            "products": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "price": 500,
                    "cost": 300,
                }
            ],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "unpaid balance" in response.json()["detail"]["message"]


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

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
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
    assert data["repair_meta"]["repair_status"] == "new"
    assert data["repair_meta"]["customer_complaint"] == "Не охлаждает"
    assert data["repair_meta"]["equipment_serial_number"] == "SN-REPAIR-1"
    diagnostic_lines = [
        line for line in data["service_lines"]
        if "Диагностика кондиционера" in line["service_title"]
    ]
    assert len(diagnostic_lines) == 1

    second_response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"workflow_type": "repair", "repair_meta": {"repair_status": "scheduled"}},
        headers=headers,
    )
    assert second_response.status_code == 200, second_response.text
    second_data = second_response.json()
    assert second_data["repair_meta"]["repair_status"] == "scheduled"
    diagnostic_lines = [
        line for line in second_data["service_lines"]
        if "Диагностика кондиционера" in line["service_title"]
    ]
    assert len(diagnostic_lines) == 1


@pytest.mark.asyncio
async def test_manager_order_patch_rejects_invalid_repair_status(async_client, db):
    customer = Customer(name="Repair Invalid Status", phone="+375295555559", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "workflow_type": "repair",
            "repair_meta": {"repair_status": "waiting_for_magic"},
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "Invalid repair_status" in response.text


@pytest.mark.asyncio
async def test_manager_order_create_repair_sets_default_status_and_diagnostic(async_client, db):
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
    db.add(tariff)
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/orders",
        json={
            "source": "manager",
            "request_text": "Клиент просит ремонт кондиционера, не охлаждает.",
            "service_type": "repair",
            "customer_type": "individual",
            "name": "Repair Create",
            "phone": "+375295555560",
            "address": "Минск",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["workflow_type"] == "repair"
    assert data["repair_meta"]["repair_status"] == "new"
    diagnostic_lines = [
        line for line in data["service_lines"]
        if "Диагностика кондиционера" in line["service_title"]
    ]
    assert len(diagnostic_lines) == 1


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
async def test_manager_repair_act_ai_draft_generates_sanitized_meta(async_client, monkeypatch):
    captured = {}

    async def _fake_request_completion(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "fault_type": "refrigerant_leak",
                "fault_location": "flare_connections",
                "repairable": True,
                "operation_status": "limited",
                "risks": ["compressor_damage"],
                "recommended_actions": ["restore_circuit_tightness", "vacuuming", "full_refrigerant_charge"],
                "refrigerant": "R410A",
                "refrigerant_amount": "790 g",
                "hidden_defects_possible": True,
                "unknown_key": "must be ignored",
            },
            ensure_ascii=False,
        )

    from services.defect_act_ai_service import DefectActAIService

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    headers = await _auth_headers(async_client)
    payload = {
        "defect_type": "refrigerant_leak",
        "defect_label": "Утечка хладагента",
        "equipment_model": "Daikin FTXB25C",
        "diagnostic_notes": "Обмерзает внутренний блок, давление ниже нормы.",
        "current_meta": {"customer_complaint": "Плохо холодит"},
    }
    response = await async_client.post("/api/manager/repair-complaints/ai-draft", json=payload, headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["provider"] == "deepseek"
    assert data["prompt_version"] == "defect_act_v3"
    assert data["repair_meta"]["fault_type"] == "refrigerant_leak"
    assert data["repair_meta"]["structured_diagnosis"]["fault_location"] == "flare_connections"
    assert data["repair_meta"]["diagnostic_result"].startswith("Выявлены признаки утечки")
    assert data["repair_meta"]["repair_recommendation"].startswith("Рекомендуется восстановить герметичность")
    assert data["repair_meta"]["repair_estimate_text"].startswith("Устранение утечки хладагента")
    assert "technical_condition" not in data["repair_meta"]
    assert "technical_conclusion" not in data["repair_meta"]
    assert "unknown_key" not in data["repair_meta"]
    assert "Утечка хладагента" in captured["prompt"]
    assert "Daikin FTXB25C" in captured["prompt"]
    assert "готовый дефектный акт" in captured["prompt"]


@pytest.mark.asyncio
async def test_manager_order_patch_title_and_labels_search(async_client, db):
    customer = Customer(name="Patch Labels", phone="+375295555557", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
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
async def test_manager_order_patch_rejects_unknown_customer_id(async_client, db):
    customer = Customer(name="Known Customer", phone="+375295533333", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"customer_id": 999999},
        headers=headers,
    )

    assert response.status_code == 400
    assert "Customer not found" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_manager_order_patch_rejects_invalid_closing_result(async_client, db):
    customer = Customer(name="Closing Result", phone="+375295544444", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"status": "closed", "closing_result": "maybe"},
        headers=headers,
    )

    assert response.status_code == 400
    assert "Invalid closing_result" in response.json()["detail"]["message"]


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
    one_time_contract_id = one_time_contract_with_open_selected.json()["doc_id"]
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
    assert first_act.status_code == 400
    assert "основан" in first_act.json()["detail"]["message"].lower()

    first_act = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        headers=headers,
        params={"base_document_id": 0},
    )
    assert first_act.status_code == 200
    assert first_act.json()["base_document_id"] is None
    assert first_act.json()["base_customer_contract_id"] == contract.id
    assert captured_replacements[-1]["{{act_number}}"] == "1"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "1"
    assert captured_replacements[-1]["{{object_address}}"] == "Минск, объект 1"
    first_act_doc = await db.get(OrderDocument, first_act.json()["doc_id"])
    assert first_act_doc is not None
    assert first_act_doc.base_document_id is None
    assert first_act_doc.base_customer_contract_id == contract.id

    second_order = Order(customer_id=customer.id, customer_contract_id=contract.id, status=OrderStatus.NEW_LEAD)
    db.add(second_order)
    await db.commit()
    await db.refresh(second_order)

    second_act = await async_client.post(f"/api/manager/orders/{second_order.id}/documents/act", headers=headers)
    assert second_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "2"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "2"

    one_time_contract_act = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        headers=headers,
        params={"base_document_id": one_time_contract_id},
    )
    assert one_time_contract_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "1"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "1"
    assert one_time_contract_act.json()["base_document_id"] == one_time_contract_id
    assert one_time_contract_act.json()["base_customer_contract_id"] is None
    one_time_contract_act_doc = await db.get(OrderDocument, one_time_contract_act.json()["doc_id"])
    assert one_time_contract_act_doc is not None
    assert one_time_contract_act_doc.base_document_id == one_time_contract_id
    assert one_time_contract_act_doc.base_customer_contract_id is None

    second_one_time_contract_act = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        headers=headers,
        params={"base_document_id": one_time_contract_id},
    )
    assert second_one_time_contract_act.status_code == 200
    assert captured_replacements[-1]["{{act_number}}"] == "2"
    assert captured_replacements[-1]["{{act_sequence_number}}"] == "2"
    assert second_one_time_contract_act.json()["base_document_id"] == one_time_contract_id


@pytest.mark.asyncio
async def test_manager_order_act_generation_can_be_scoped_to_object_and_service_lines(async_client, db, monkeypatch):
    customer = Customer(name="Scoped Act Company", phone="+375296001133", type=CustomerType.company, inn="123456780")
    contract = CustomerContract(
        customer=customer,
        number="ОД-2026-900",
        valid_from=datetime(2026, 1, 1),
        valid_until=datetime(2026, 12, 31),
        status="active",
        google_file_id="open-contract",
        google_edit_url="https://docs.google.com/document/d/open-contract/edit",
    )
    branch = CustomerBranch(customer=customer, name="Полоцк", delivery_address="Полоцк, Скорины 8А")
    order = Order(customer=customer, customer_contract=contract, customer_branch=branch, delivery_address="Минск, старый объект")
    db.add_all([customer, contract, branch, order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(branch)

    service_a = Service(title="Монтаж кондиционера", slug="scoped-act-install", base_price=300)
    service_b = Service(title="Демонтаж кондиционера", slug="scoped-act-dismantle", base_price=150)
    db.add_all([service_a, service_b])
    await db.commit()
    await db.refresh(service_a)
    await db.refresh(service_b)

    service_link_a = OrderServiceLink(order_id=order.id, service_id=service_a.id, quantity=1, price=300, cost=100)
    service_link_b = OrderServiceLink(order_id=order.id, service_id=service_b.id, quantity=2, price=150, cost=50)
    db.add_all([service_link_a, service_link_b])
    await db.commit()
    await db.refresh(service_link_a)
    await db.refresh(service_link_b)

    captured_replacements = []
    table_captures = []

    class _FakeGoogleService:
        creds = object()

        def copy_template(self, template_id, title):
            return {
                "file_id": "scoped-act-file",
                "edit_url": "https://docs.google.com/document/d/scoped-act-file/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            captured_replacements.append(dict(replacements))

        def _fill_table(self, docs_service, file_id, table_data, has_footer):
            table_captures.append(table_data)

    from services import document_service
    import googleapiclient.discovery

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: object())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        headers=headers,
        params=[
            ("base_document_id", "0"),
            ("scope_customer_branch_id", str(branch.id)),
            ("scope_service_line_ids", str(service_link_b.id)),
            ("scope_service_line_quantities", json.dumps([{"service_line_id": service_link_b.id, "quantity": 1}])),
        ],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope_customer_branch_id"] == branch.id
    assert payload["scope_title"] == "Полоцк"
    assert payload["scope_address"] == "Полоцк, Скорины 8А"

    generated_replacements = next(item for item in reversed(captured_replacements) if "{{object_address}}" in item)
    assert generated_replacements["{{object_name}}"] == "Полоцк"
    assert generated_replacements["{{object_address}}"] == "Полоцк, Скорины 8А"
    assert generated_replacements["{{total_amount}}"] == "150.00"
    assert table_captures[-1][0][1] == "Демонтаж кондиционера"
    assert table_captures[-1][0][3] == "1"
    assert table_captures[-1][-1][-1] == "150.00"

    doc = await db.get(OrderDocument, payload["doc_id"])
    assert doc is not None
    assert doc.scope_customer_branch_id == branch.id
    assert doc.scope_meta["service_line_ids"] == [service_link_b.id]
    assert doc.scope_meta["service_line_quantities"] == {str(service_link_b.id): 1}


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
    product = Product(title="P", slug="prod-p", price=3000, specs={"area_m2": 30})
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
async def test_manager_order_patch_product_price_preserves_supply_request_link(async_client, db):
    customer = Customer(name="Supply linked", phone="+375296666669", type=CustomerType.individual)
    product = Product(title="Supply linked product", slug="supply-linked-product", price=2490, specs={"area_m2": 35})
    supplier = Supplier(name="Supply linked supplier", code="supply-linked-order-update")
    db.add(customer)
    db.add(product)
    db.add(supplier)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(supplier)

    order = Order(customer_id=customer.id, status=OrderStatus.EXECUTION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    order_line = OrderProductLink(
        order_id=order.id,
        product_id=product.id,
        quantity=1,
        price=1990,
        cost=1110,
    )
    db.add(order_line)
    await db.commit()
    await db.refresh(order_line)

    supply_request = SupplyRequest(supplier_id=supplier.id)
    db.add(supply_request)
    await db.commit()
    await db.refresh(supply_request)

    supply_line = SupplyRequestLine(
        request_id=supply_request.id,
        order_product_link_id=order_line.id,
        source_type="order",
        product_id=product.id,
        title_snapshot=product.title,
        qty=1,
    )
    db.add(supply_line)
    await db.commit()
    await db.refresh(supply_line)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {
                    "link_id": order_line.id,
                    "product_id": product.id,
                    "quantity": 1,
                    "price": 2090,
                    "cost": 1110,
                }
            ]
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["product_lines"][0]["id"] == order_line.id
    assert response.json()["product_lines"][0]["price"] == 2090

    await db.refresh(order_line)
    await db.refresh(supply_line)
    assert order_line.price == 2090
    assert supply_line.order_product_link_id == order_line.id


@pytest.mark.asyncio
async def test_manager_order_patch_lines_persists_logistics_components(async_client, db):
    customer = Customer(name="Logistics", phone="+375296666668", type=CustomerType.individual)
    product = Product(title="Split Logistics", slug="split-logistics", price=1803, specs={"area_m2": 30})
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "products": [
            {
                "product_id": product.id,
                "quantity": 1,
                "price": 1803,
                "cost": 1200,
                "logistics_components": [
                    {
                        "title": "Внутренний блок TEST-IN",
                        "country": "Китай",
                        "unit": "шт.",
                        "quantity_per_parent": 1,
                        "unit_price": 600,
                        "kind": "indoor",
                    },
                    {
                        "title": "Наружный блок TEST-OUT",
                        "country": "Китай",
                        "unit": "шт.",
                        "quantity_per_parent": 1,
                        "unit_price": 1203,
                        "kind": "outdoor",
                    },
                ],
            }
        ],
        "services": [],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200

    product_lines = response.json()["product_lines"]
    assert product_lines[0]["logistics_components"] == payload["products"][0]["logistics_components"]

    await db.refresh(product)
    assert product.specs["logistics_components"] == [
        {
            "title": "Внутренний блок TEST-IN",
            "country": "Китай",
            "unit": "шт.",
            "quantity_per_parent": 1,
            "price_weight": 600.0,
            "kind": "indoor",
        },
        {
            "title": "Наружный блок TEST-OUT",
            "country": "Китай",
            "unit": "шт.",
            "quantity_per_parent": 1,
            "price_weight": 1203.0,
            "kind": "outdoor",
        },
    ]


@pytest.mark.asyncio
async def test_manager_order_patch_lines_does_not_overwrite_product_logistics_template(async_client, db):
    customer = Customer(name="Logistics Existing", phone="+375296666665", type=CustomerType.individual)
    existing_template = [
        {
            "title": "Заводской внутренний блок",
            "country": "Китай",
            "unit": "шт.",
            "quantity_per_parent": 1,
            "price_weight": 1.0,
            "kind": "indoor",
        }
    ]
    product = Product(
        title="Split Logistics Existing",
        slug="split-logistics-existing",
        price=2000,
        specs={"area_m2": 30, "logistics_components": existing_template},
    )
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    response = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "price": 2000,
                    "cost": 1200,
                    "logistics_components": [
                        {
                            "title": "Ручной блок из заказа",
                            "country": "Китай",
                            "unit": "шт.",
                            "quantity_per_parent": 1,
                            "unit_price": 2000,
                            "kind": "outdoor",
                        }
                    ],
                }
            ],
            "services": [],
        },
        headers=headers,
    )
    assert response.status_code == 200

    await db.refresh(product)
    assert product.specs["logistics_components"] == existing_template


@pytest.mark.asyncio
async def test_manager_order_proposals_can_duplicate_edit_and_select(async_client, db):
    customer = Customer(name="Proposal Customer", phone="+375296666667", type=CustomerType.individual)
    p1 = Product(title="Proposal P1", slug="proposal-p1", price=1000, specs={"area_m2": 25})
    p2 = Product(title="Proposal P2", slug="proposal-p2", price=2000, specs={"area_m2": 35})
    s1 = Service(title="Proposal S1", slug="proposal-s1", category="maintenance", base_price=100)
    s2 = Service(title="Proposal S2", slug="proposal-s2", base_price=300)
    db.add(customer)
    db.add(p1)
    db.add(p2)
    db.add(s1)
    db.add(s2)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(p1)
    await db.refresh(p2)
    await db.refresh(s1)
    await db.refresh(s2)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    first_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [{"product_id": p1.id, "quantity": 1, "price": 1000, "cost": 700}],
            "services": [{"service_id": s1.id, "title": s1.title, "quantity": 1, "price": 100, "cost": 60}],
        },
        headers=headers,
    )
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert len(first_data["proposals"]) == 1
    default_proposal = first_data["proposals"][0]
    assert default_proposal["is_selected"] is True
    assert default_proposal["total_amount"] == 1100

    duplicate_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{default_proposal['id']}/duplicate",
        json={"name": "Вариант 2"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 200
    duplicate_data = duplicate_resp.json()
    second_proposal = next(item for item in duplicate_data["proposals"] if item["name"] == "Вариант 2")
    assert second_proposal["total_amount"] == 1100

    edit_second_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {"product_id": p2.id, "quantity": 1, "price": 2000, "cost": 1300, "proposal_id": second_proposal["id"]},
            ],
            "services": [
                {
                    "service_id": s2.id,
                    "title": s2.title,
                    "quantity": 1,
                    "price": 300,
                    "cost": 120,
                    "proposal_id": second_proposal["id"],
                },
            ],
        },
        headers=headers,
    )
    assert edit_second_resp.status_code == 200
    edit_second_data = edit_second_resp.json()
    updated_second = next(item for item in edit_second_data["proposals"] if item["id"] == second_proposal["id"])
    assert updated_second["total_amount"] == 2300
    assert edit_second_data["product_lines"][0]["product_id"] == p1.id
    assert edit_second_data["service_lines"][0]["service_id"] == s1.id
    assert edit_second_data["service_lines"][0]["service_category"] == "maintenance"

    select_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{second_proposal['id']}/select",
        headers=headers,
    )
    assert select_resp.status_code == 200
    selected_data = select_resp.json()
    assert selected_data["total_amount"] == 2300
    assert selected_data["margin"] == 880
    assert selected_data["product_lines"][0]["product_id"] == p2.id
    assert selected_data["service_lines"][0]["service_id"] == s2.id
    assert next(item for item in selected_data["proposals"] if item["id"] == second_proposal["id"])["is_selected"] is True

    first_after_select = next(item for item in selected_data["proposals"] if item["id"] == default_proposal["id"])
    second_after_select = next(item for item in selected_data["proposals"] if item["id"] == second_proposal["id"])
    assert [line["product_id"] for line in first_after_select["product_lines"]] == [p1.id]
    assert [line["service_id"] for line in first_after_select["service_lines"]] == [s1.id]
    assert [line["product_id"] for line in second_after_select["product_lines"]] == [p2.id]
    assert [line["service_id"] for line in second_after_select["service_lines"]] == [s2.id]

    select_first_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals/{default_proposal['id']}/select",
        headers=headers,
    )
    assert select_first_resp.status_code == 200
    selected_first_data = select_first_resp.json()
    assert selected_first_data["total_amount"] == 1100
    assert selected_first_data["margin"] == 340
    assert selected_first_data["product_lines"][0]["product_id"] == p1.id
    assert selected_first_data["service_lines"][0]["service_id"] == s1.id

    first_after_return = next(item for item in selected_first_data["proposals"] if item["id"] == default_proposal["id"])
    second_after_return = next(item for item in selected_first_data["proposals"] if item["id"] == second_proposal["id"])
    assert [line["product_id"] for line in first_after_return["product_lines"]] == [p1.id]
    assert [line["service_id"] for line in first_after_return["service_lines"]] == [s1.id]
    assert [line["product_id"] for line in second_after_return["product_lines"]] == [p2.id]
    assert [line["service_id"] for line in second_after_return["service_lines"]] == [s2.id]

    list_resp = await async_client.get("/api/manager/orders?segment=b2c", headers=headers)
    assert list_resp.status_code == 200
    list_item = next(item for item in list_resp.json()["items"] if item["id"] == order.id)
    assert list_item["total_amount"] == 1100
    assert list_item["margin"] == 340


@pytest.mark.asyncio
async def test_manager_proposal_lifecycle_validates_and_protects_sent_revision(async_client, db):
    customer = Customer(name="Lifecycle Customer", phone="+375296666668", type=CustomerType.individual)
    product = Product(title="Lifecycle Product", slug="lifecycle-product", price=1200, specs={"area_m2": 25})
    db.add_all([customer, product])
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    headers = await _auth_headers(async_client)

    create_lines = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": product.id, "quantity": 1, "price": 1200, "cost": 700}]},
        headers=headers,
    )
    assert create_lines.status_code == 200
    proposal = create_lines.json()["proposals"][0]

    empty_variant = await async_client.post(
        f"/api/manager/orders/{order.id}/proposals",
        json={"name": "Пустой вариант"},
        headers=headers,
    )
    assert empty_variant.status_code == 200
    empty_proposal = next(item for item in empty_variant.json()["proposals"] if item["name"] == "Пустой вариант")
    empty_ready = await async_client.patch(
        f"/api/manager/orders/{order.id}/proposals/{empty_proposal['id']}",
        json={"status": "ready_to_send"},
        headers=headers,
    )
    assert empty_ready.status_code == 400

    ready = await async_client.patch(
        f"/api/manager/orders/{order.id}/proposals/{proposal['id']}",
        json={"status": "ready_to_send"},
        headers=headers,
    )
    assert ready.status_code == 200
    assert ready.json()["proposal_status"] == "ready_to_send"
    assert ready.json()["negotiation_status"] == "awaiting_offer"

    invalid = await async_client.patch(
        f"/api/manager/orders/{order.id}/proposals/{proposal['id']}",
        json={"status": "unknown"},
        headers=headers,
    )
    assert invalid.status_code == 400

    sent = await async_client.patch(
        f"/api/manager/orders/{order.id}/proposals/{proposal['id']}",
        json={"status": "sent"},
        headers=headers,
    )
    assert sent.status_code == 200
    assert sent.json()["proposal_status"] == "sent"
    assert sent.json()["negotiation_status"] == "proposal_sent"

    locked_edit = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": product.id, "quantity": 2, "price": 1200, "cost": 700}]},
        headers=headers,
    )
    assert locked_edit.status_code == 400
    assert "cannot be edited" in str(locked_edit.json())

    draft = await async_client.patch(
        f"/api/manager/orders/{order.id}/proposals/{proposal['id']}",
        json={"status": "draft"},
        headers=headers,
    )
    assert draft.status_code == 200
    assert draft.json()["proposal_status"] == "draft"
    editable_again = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": product.id, "quantity": 2, "price": 1200, "cost": 700}]},
        headers=headers,
    )
    assert editable_again.status_code == 200
    assert editable_again.json()["total_amount"] == 2400


@pytest.mark.asyncio
async def test_manager_order_export_preview_and_import_creates_new_order(async_client, db):
    customer = Customer(name="Transfer Customer", phone="+375291234000", type=CustomerType.individual)
    product = Product(title="Transfer Product", slug="transfer-product", price=1800, specs={"area_m2": 25})
    service = Service(title="Transfer Service", slug="transfer-service", base_price=250)
    installer = Installer(name="Transfer Installer", is_active=True)
    db.add(customer)
    db.add(product)
    db.add(service)
    db.add(installer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)
    await db.refresh(installer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.EXECUTION,
        title="Переносимый заказ",
        comment="Собран на локальном сервере",
        auto_close_on_payment=True,
        execution_status="work_done",
        execution_status_changed_at=datetime.now() - timedelta(hours=2),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    patch_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [{"product_id": product.id, "quantity": 2, "price": 1700, "cost": 1100}],
            "services": [{"service_id": service.id, "title": service.title, "quantity": 1, "price": 250, "cost": 100}],
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    db.add(Payment(order_id=order.id, amount=500, currency=PaymentCurrency.BYN, comment="Аванс"))
    db.add(
        OrderWorkStage(
            order_id=order.id,
            name="Монтаж",
            status=OrderStageStatus.PLANNED,
            installer_id=installer.id,
            manager_comment="Проверить перенос",
        )
    )
    await db.commit()

    export_resp = await async_client.post(
        "/api/manager/orders/export",
        json={"order_ids": [order.id], "include_payments": True, "include_work_stages": True},
        headers=headers,
    )
    assert export_resp.status_code == 200, export_resp.text
    package = export_resp.json()
    assert package["orders"][0]["source_id"] == order.id
    assert package["orders"][0]["payments"][0]["amount"] == 500
    assert package["orders"][0]["status"] == "execution"
    assert package["orders"][0]["auto_close_on_payment"] is True
    assert package["orders"][0]["execution_status"] == "work_done"
    assert package["orders"][0]["execution_status_changed_at"] is not None

    preview_resp = await async_client.post(
        "/api/manager/orders/import/preview",
        json={"package": package},
        headers=headers,
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()
    assert preview["orders_count"] == 1
    assert preview["products_missing"] == 0
    assert preview["can_import"] is True
    assert preview["customers"][0]["status"] == "matched"

    import_resp = await async_client.post(
        "/api/manager/orders/import",
        json={"package": package},
        headers=headers,
    )
    assert import_resp.status_code == 200, import_resp.text
    imported_id = import_resp.json()["created_order_ids"][0]
    assert imported_id != order.id

    detail_resp = await async_client.get(f"/api/manager/orders/{imported_id}", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert detail["title"] == "Переносимый заказ"
    assert detail["customer"]["id"] == customer.id
    assert detail["product_lines"][0]["product_id"] == product.id
    assert detail["product_lines"][0]["quantity"] == 2
    assert detail["service_lines"][0]["service_id"] == service.id
    assert detail["payments"][0]["amount"] == 500
    assert detail["work_stages"][0]["name"] == "Монтаж"
    assert detail["status"] == "execution"
    assert detail["auto_close_on_payment"] is True
    assert detail["execution_status"] == "work_done"
    assert detail["execution_status_changed_at"] is not None
    assert detail["total_amount"] == 3650


@pytest.mark.asyncio
async def test_manager_order_import_preview_blocks_missing_products(async_client, db):
    customer = Customer(name="Transfer Missing", phone="+375291234001", type=CustomerType.individual)
    product = Product(title="Existing Transfer Product", slug="existing-transfer-product", price=900, specs={"area_m2": 20})
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    patch_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={"products": [{"product_id": product.id, "quantity": 1, "price": 900, "cost": 600}], "services": []},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    export_resp = await async_client.post(
        "/api/manager/orders/export",
        json={"order_ids": [order.id]},
        headers=headers,
    )
    assert export_resp.status_code == 200, export_resp.text
    package = export_resp.json()
    product_ref = package["orders"][0]["proposals"][0]["product_lines"][0]["product"]
    product_ref["title"] = "Definitely Missing Product"
    product_ref["slug"] = "definitely-missing-product"
    product_ref["source_url"] = None

    preview_resp = await async_client.post(
        "/api/manager/orders/import/preview",
        json={"package": package},
        headers=headers,
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()
    assert preview["products_missing"] == 1
    assert preview["can_import"] is False

    import_resp = await async_client.post(
        "/api/manager/orders/import",
        json={"package": package},
        headers=headers,
    )
    assert import_resp.status_code == 400


@pytest.mark.asyncio
async def test_manager_order_offer_generation_uses_requested_proposal_and_creates_each_time(async_client, db, monkeypatch):
    customer = Customer(name="Proposal Docs", phone="+375296666668", type=CustomerType.individual)
    p1 = Product(title="Proposal Doc P1", slug="proposal-doc-p1", price=1000, specs={"area_m2": 25})
    p2 = Product(title="Proposal Doc P2", slug="proposal-doc-p2", price=2000, specs={"area_m2": 35})
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

    order_after_generation = await async_client.get(
        f"/api/manager/orders/{order.id}",
        headers=headers,
    )
    assert order_after_generation.status_code == 200
    order_payload = order_after_generation.json()
    assert order_payload["proposal_status"] == "draft"
    assert {proposal["status"] for proposal in order_payload["proposals"]} == {"draft"}


@pytest.mark.asyncio
async def test_manager_order_tn2_generation_uses_requested_proposal_logistics_components(async_client, db, monkeypatch):
    customer = Customer(name="Waybill Proposal", phone="+375296666669", type=CustomerType.individual)
    p1 = Product(title="Waybill P1", slug="waybill-p1", price=1000, specs={"area_m2": 25})
    p2 = Product(title="Waybill P2", slug="waybill-p2", price=1803, specs={"area_m2": 35})
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
        json={"name": "Накладная"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 200
    second_proposal = next(item for item in duplicate_resp.json()["proposals"] if item["name"] == "Накладная")

    edit_second_resp = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={
            "products": [
                {
                    "product_id": p2.id,
                    "quantity": 1,
                    "price": 1803,
                    "cost": 1300,
                    "proposal_id": second_proposal["id"],
                    "logistics_components": [
                        {
                            "title": "Внутренний блок WAY-IN",
                            "country": "Китай",
                            "unit": "шт.",
                            "quantity_per_parent": 1,
                            "unit_price": 600,
                            "kind": "indoor",
                        },
                        {
                            "title": "Наружный блок WAY-OUT",
                            "country": "Китай",
                            "unit": "шт.",
                            "quantity_per_parent": 1,
                            "unit_price": 1203,
                            "kind": "outdoor",
                        },
                    ],
                },
            ],
            "services": [],
        },
        headers=headers,
    )
    assert edit_second_resp.status_code == 200

    contract = OrderDocument(
        order_id=order.id,
        doc_type="contract",
        number="Д-TEST",
        date=datetime.now(),
        google_file_id="contract-file",
        google_edit_url="https://docs.google.com/document/d/contract-file/edit",
    )
    db.add(contract)
    await db.commit()

    sheet_captures = []

    class _FakeGoogleSheetService:
        def generate_sheet(
            self,
            template_id,
            doc_title,
            replacements,
            table_rows,
            start_cell_addr,
            target_sheet_name,
            merge_cols,
            draw_borders,
            sheet_format_ranges=None,
        ):
            _ = (
                template_id,
                doc_title,
                replacements,
                start_cell_addr,
                target_sheet_name,
                merge_cols,
                draw_borders,
                sheet_format_ranges,
            )
            sheet_captures.append(table_rows)
            return f"https://docs.google.com/spreadsheets/d/waybill-{len(sheet_captures)}/edit"

    from services.documents import logistics

    monkeypatch.setattr(logistics, "get_google_service", lambda: _FakeGoogleSheetService())

    first_tn2_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/tn2",
        params={"proposal_id": second_proposal["id"]},
        headers=headers,
    )
    assert first_tn2_resp.status_code == 200, first_tn2_resp.text
    first_tn2 = first_tn2_resp.json()
    assert first_tn2["proposal_id"] == second_proposal["id"]
    assert sheet_captures[-1][0][0].startswith("Внутренний блок WAY-IN")
    assert sheet_captures[-1][1][0].startswith("Наружный блок WAY-OUT")
    assert "Waybill P1" not in "\n".join(str(cell) for row in sheet_captures[-1] for cell in row)

    second_tn2_resp = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/tn2",
        params={"proposal_id": second_proposal["id"]},
        headers=headers,
    )
    assert second_tn2_resp.status_code == 200, second_tn2_resp.text
    assert second_tn2_resp.json()["doc_id"] != first_tn2["doc_id"]


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
async def test_manager_order_payment_unknown_order_returns_404(async_client):
    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/orders/999999/payments",
        headers=headers,
        json={"amount": 100, "type": "postpayment"},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error_code"] == "order_not_found"
    assert detail["message"] == "Order not found"


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
        base_document_id=None,
        **kwargs,
    ):
        _ = (session, order_id, doc_type, document_template_id, template_id, proposal_id, base_document_id, kwargs)
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
async def test_manager_doc_download_returns_pdf_bytes(async_client, db, monkeypatch):
    customer = Customer(name="Download", phone="+375297777777", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    document = OrderDocument(
        order_id=order.id,
        doc_type="contract",
        number="Д-2026-001",
        date=datetime(2026, 6, 4),
        google_file_id="google-doc-id",
        google_edit_url="https://docs.google.com/document/d/google-doc-id/edit",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    pdf_bytes = b"%PDF-1.4\n%real pdf bytes\n%%EOF"

    class _FakeGoogleService:
        def export_file(self, file_id: str, mime_type: str = "application/pdf"):
            assert file_id == "google-doc-id"
            assert mime_type == "application/pdf"
            return BytesIO(pdf_bytes)

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/docs/{document.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == pdf_bytes
    assert "filename*=UTF-8''" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_document_numbering_uses_shared_prefix_sequence_per_year(db):
    from services.document_service import DocumentService

    customer = Customer(name="Numbering", phone="+375297777777", type=CustomerType.individual)
    order = Order(customer=customer, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add_all(
        [
            OrderDocument(
                order_id=order.id,
                doc_type="contract",
                number="Д-2026-001",
                date=datetime(2026, 1, 10),
                google_file_id="contract-a",
                google_edit_url="https://example.com/contract-a",
            ),
            OrderDocument(
                order_id=order.id,
                doc_type="contract",
                number="Д-2025-999",
                date=datetime(2025, 12, 31),
                google_file_id="contract-old",
                google_edit_url="https://example.com/contract-old",
            ),
        ]
    )
    await db.commit()

    assert await DocumentService._get_next_number(db, "contract", datetime(2026, 5, 1)) == "Д-2026-002"
    assert await DocumentService._get_next_number(db, "contract", datetime(2027, 1, 1)) == "Д-2027-001"


@pytest.mark.asyncio
async def test_manager_order_act_can_use_invoice_as_base_document(async_client, db, monkeypatch):
    customer = Customer(name="Invoice Base", phone="+375297777777", type=CustomerType.individual)
    order = Order(customer=customer, status=OrderStatus.NEGOTIATION, total_amount=200)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-005",
        date=datetime(2026, 5, 10),
        google_file_id="invoice-file",
        google_edit_url="https://example.com/invoice",
    )
    invoice_template = DocumentTemplate(
        name="Счет-договор",
        doc_type="invoice",
        google_template_id="invoice-template",
        base_document_type_label="Счет-договор",
    )
    db.add(invoice_template)
    await db.commit()
    await db.refresh(invoice_template)
    invoice.document_template_id = invoice_template.id
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            captured["template_id"] = template_id
            captured["title"] = title
            return {"file_id": "fake-act", "edit_url": "https://docs.google.com/document/d/fake-act/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["file_id"] = file_id
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        params={"contract_date": "2026-05-20T00:00:00", "base_document_id": invoice.id},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["base_document_id"] == invoice.id
    replacements = captured["replacements"]
    assert replacements["{{base_document_type}}"] == "Счет-договор"
    assert replacements["{{base_document_number}}"] == "С-2026-005"
    assert replacements["{{base_document_date}}"] == "10.05.2026"
    assert replacements["{{invoice_number}}"] == "С-2026-005"

    result = await db.execute(select(OrderDocument).where(OrderDocument.doc_type == "act"))
    act = result.scalars().first()
    assert act.base_document_id == invoice.id
    order_id = order.id
    customer_id = customer.id
    act_id = act.id

    docs_response = await async_client.get(f"/api/manager/orders/{order_id}/documents", headers=headers)
    assert docs_response.status_code == 200
    act_item = next(item for item in docs_response.json()["items"] if item["id"] == act_id)
    assert act_item["base_document_type"] == "invoice"
    assert act_item["base_document_type_label"] == "Счет-договор"

    db.expire_all()

    detail_response = await async_client.get(f"/api/manager/orders/{order_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_act_item = next(item for item in detail_response.json()["documents"] if item["id"] == act_id)
    assert detail_act_item["base_document_type"] == "invoice"
    assert detail_act_item["base_document_type_label"] == "Счет-договор"

    customer_docs_response = await async_client.get(f"/api/manager/customers/{customer_id}/docs", headers=headers)
    assert customer_docs_response.status_code == 200
    customer_act_item = next(item for item in customer_docs_response.json()["items"] if item["id"] == act_id)
    assert customer_act_item["base_document_type"] == "invoice"
    assert customer_act_item["base_document_type_label"] == "Счет-договор"


@pytest.mark.asyncio
async def test_manager_customer_reconciliation_groups_documents_and_payments(async_client, db):
    customer = Customer(name='ООО "Сверка"', phone="+375297777778", type=CustomerType.company, inn="192663084")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order_before = Order(
        customer_id=customer.id,
        status=OrderStatus.CLOSED,
        title="Старый заказ",
        total_amount=300,
        balance_due=100,
        created_at=datetime(2025, 12, 20),
        contract_date=datetime(2025, 12, 20),
    )
    order_inside = Order(
        customer_id=customer.id,
        status=OrderStatus.CLOSED,
        title="Монтаж",
        total_amount=1200,
        balance_due=700,
        created_at=datetime(2026, 2, 1),
        contract_date=datetime(2026, 2, 1),
        delivery_address="Витебск, ул. Ленина, д. 1",
    )
    db.add_all([order_before, order_inside])
    await db.commit()
    await db.refresh(order_before)
    await db.refresh(order_inside)

    db.add_all(
        [
            OrderDocument(
                order_id=order_before.id,
                doc_type="act",
                number="1",
                date=datetime(2025, 12, 21),
                google_file_id="old-act",
                google_edit_url="https://example.com/old-act",
            ),
            OrderDocument(
                order_id=order_inside.id,
                doc_type="act",
                number="2",
                date=datetime(2026, 2, 2),
                google_file_id="act",
                google_edit_url="https://example.com/act",
            ),
            OrderDocument(
                order_id=order_inside.id,
                doc_type="tn2",
                number="3",
                date=datetime(2026, 2, 2),
                google_file_id="tn2",
                google_edit_url="https://example.com/tn2",
            ),
        ]
    )
    receipt = BankReceipt(
        status="matched",
        sender_email="bank@example.com",
        subject="Платеж",
        fingerprint="reconciliation-payment",
        received_at=datetime(2026, 2, 5),
        our_account="BY00TEST",
        amount=500,
        currency=PaymentCurrency.BYN,
        payer_name='ООО "Сверка"',
        payer_unp="192663084",
        payer_account="BY99PAYER",
        payment_document_number="42",
        payment_document_raw="ПП №42",
        payment_purpose="Оплата по договору",
        raw_body="body",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    db.add_all(
        [
            Payment(order_id=order_before.id, amount=200, currency=PaymentCurrency.BYN, date=datetime(2025, 12, 25)),
            Payment(
                order_id=order_inside.id,
                bank_receipt_id=receipt.id,
                amount=500,
                currency=PaymentCurrency.BYN,
                date=datetime(2026, 2, 5),
            ),
        ]
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        f"/api/manager/customers/{customer.id}/reconciliation",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["opening_balance"] == 100
    assert data["documents_total"] == 1200
    assert data["payments_total"] == 500
    assert data["closing_balance"] == 800
    assert len(data["documents"]) == 1
    assert data["documents"][0]["order_id"] == order_inside.id
    assert data["documents"][0]["basis"] == "Акт №2, ТН-2 №3"
    assert len(data["documents"][0]["documents"]) == 2
    assert len(data["payments"]) == 1
    assert data["payments"][0]["payment_document_number"] == "42"
    assert data["payments"][0]["payer_account"] == "BY99PAYER"


@pytest.mark.asyncio
async def test_manager_customer_reconciliation_counts_split_bank_receipt_once(async_client, db):
    customer = Customer(
        name='ООО "Сверка распределения"',
        phone="+375297777780",
        type=CustomerType.company,
        inn="192663085",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    orders = [
        Order(
            customer_id=customer.id,
            status=OrderStatus.CLOSED,
            title="Акт 1",
            total_amount=500,
            created_at=datetime(2026, 7, 1),
        ),
        Order(
            customer_id=customer.id,
            status=OrderStatus.CLOSED,
            title="Акт 2",
            total_amount=880,
            created_at=datetime(2026, 7, 2),
        ),
    ]
    db.add_all(orders)
    await db.commit()
    for order in orders:
        await db.refresh(order)
    receipt = BankReceipt(
        status="partially_allocated",
        sender_email="bank@example.com",
        subject="Платеж с переплатой",
        fingerprint="reconciliation-split-payment",
        received_at=datetime(2026, 7, 5),
        amount=1400,
        currency=PaymentCurrency.BYN,
        payer_name=customer.name,
        payer_unp=customer.inn,
        payment_document_number="43",
        payment_purpose="Оплата двух актов",
        raw_body="body",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    db.add_all(
        [
            Payment(
                order_id=orders[0].id,
                bank_receipt_id=receipt.id,
                amount=500,
                currency=PaymentCurrency.BYN,
                date=receipt.received_at,
            ),
            Payment(
                order_id=orders[1].id,
                bank_receipt_id=receipt.id,
                amount=880,
                currency=PaymentCurrency.BYN,
                date=receipt.received_at,
            ),
        ]
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        f"/api/manager/customers/{customer.id}/reconciliation",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["documents_total"] == 1380
    assert data["payments_total"] == 1400
    assert data["closing_balance"] == -20
    assert len(data["payments"]) == 1
    assert data["payments"][0]["amount"] == 1400
    assert data["payments"][0]["allocated_amount"] == 1380


@pytest.mark.asyncio
async def test_manager_customer_reconciliation_document_generation(async_client, db, monkeypatch):
    customer = Customer(
        name='ООО "Док сверки"',
        full_legal_name='Общество с ограниченной ответственностью "Док сверки"',
        phone="+375297777779",
        type=CustomerType.company,
        inn="192663085",
        legal_address="г. Витебск, ул. Советская, д. 1",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.CLOSED,
        title="Поставка и монтаж",
        total_amount=900,
        created_at=datetime(2026, 3, 1),
        contract_date=datetime(2026, 3, 1),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add_all(
        [
            OrderDocument(
                order_id=order.id,
                doc_type="act",
                number="4",
                date=datetime(2026, 3, 2),
                google_file_id="act-4",
                google_edit_url="https://example.com/act-4",
            ),
            Payment(order_id=order.id, amount=400, currency=PaymentCurrency.BYN, date=datetime(2026, 3, 5)),
        ]
    )
    await db.commit()

    captured = {}

    class _FakeGoogleService:
        def create_document_from_html(self, title, html):
            captured["title"] = title
            captured["html"] = html
            return {"file_id": "reconciliation-file", "edit_url": "https://docs.google.com/document/d/reconciliation-file/edit"}

    from services import customer_reconciliation_service

    monkeypatch.setattr(customer_reconciliation_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/customers/{customer.id}/reconciliation/document",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["file_id"] == "reconciliation-file"
    assert data["edit_url"].endswith("/edit")
    assert "Акт сверки" in captured["title"]
    assert "Акт сверки взаимных расчетов" in captured["html"]
    assert "Дебет, BYN" in captured["html"]
    assert "Кредит, BYN" in captured["html"]
    assert "Акт №4" in captured["html"]
    assert "Задолженность в пользу ИП Янулевич Д.В. составляет 500,00 BYN." in captured["html"]


@pytest.mark.asyncio
async def test_manager_order_waybills_can_use_invoice_as_base_document(async_client, db, monkeypatch):
    customer = Customer(name="Waybill Base", phone="+375297777777", type=CustomerType.individual)
    product = Product(title="Кондиционер", slug="base-waybill-product", price=1000)
    order = Order(customer=customer, status=OrderStatus.NEGOTIATION, total_amount=1000)
    db.add_all([customer, product, order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(product)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-006",
        date=datetime(2026, 5, 11),
        google_file_id="invoice-file",
        google_edit_url="https://example.com/invoice",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    captured = {}

    class _FakeGoogleService:
        def generate_sheet(
            self,
            template_id,
            doc_title,
            replacements,
            table_rows,
            start_cell_addr,
            target_sheet_name,
            merge_cols,
            draw_borders=True,
            sheet_format_ranges=None,
        ):
            captured.setdefault("calls", []).append(
                {
                    "template_id": template_id,
                    "title": doc_title,
                    "replacements": replacements,
                    "table_rows": table_rows,
                    "sheet": target_sheet_name,
                }
            )
            return f"https://docs.google.com/spreadsheets/d/fake-{target_sheet_name}/edit"

    from services.documents import logistics

    monkeypatch.setattr(logistics, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    for doc_type in ("tn2", "ttn1"):
        response = await async_client.post(
            f"/api/manager/orders/{order.id}/documents/{doc_type}",
            params={"contract_date": "2026-05-21T00:00:00", "base_document_id": invoice.id},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["base_document_id"] == invoice.id

    assert [call["replacements"]["{{base_document_number}}"] for call in captured["calls"]] == [
        "С-2026-006",
        "С-2026-006",
    ]
    result = await db.execute(select(OrderDocument).where(OrderDocument.doc_type.in_(["tn2", "ttn1"])))
    docs = result.scalars().all()
    assert {doc.base_document_id for doc in docs} == {invoice.id}


@pytest.mark.asyncio
async def test_manager_order_requires_selected_base_document_when_multiple_exist(async_client, db, monkeypatch):
    customer = Customer(name="Multi Base", phone="+375297777777", type=CustomerType.individual)
    order = Order(customer=customer, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    invoice_a = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-007",
        date=datetime(2026, 5, 12),
        google_file_id="invoice-a",
        google_edit_url="https://example.com/invoice-a",
    )
    invoice_b = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-008",
        date=datetime(2026, 5, 13),
        google_file_id="invoice-b",
        google_edit_url="https://example.com/invoice-b",
    )
    db.add_all([invoice_a, invoice_b])
    await db.commit()
    await db.refresh(invoice_b)

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {"file_id": "fake-act-selected", "edit_url": "https://docs.google.com/document/d/fake-act-selected/edit"}

        def replace_placeholders(self, file_id, replacements):
            pass

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    missing_response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        params={"contract_date": "2026-05-22T00:00:00"},
        headers=headers,
    )
    assert missing_response.status_code == 400
    assert "основание" in missing_response.json()["detail"]["message"]

    selected_response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        params={"contract_date": "2026-05-22T00:00:00", "base_document_id": invoice_b.id},
        headers=headers,
    )
    assert selected_response.status_code == 200, selected_response.text
    assert selected_response.json()["base_document_id"] == invoice_b.id


@pytest.mark.asyncio
async def test_manager_order_closing_doc_keeps_open_contract_base_after_order_contract_changes(async_client, db, monkeypatch):
    customer = Customer(name='ООО "Стабильность"', phone="+375297777777", type=CustomerType.company)
    contract_a = CustomerContract(
        customer=customer,
        number="ОД-2026-А",
        valid_from=datetime(2026, 1, 15),
        valid_until=datetime(2027, 1, 15),
        status="active",
    )
    contract_b = CustomerContract(
        customer=customer,
        number="ОД-2026-Б",
        valid_from=datetime(2026, 2, 20),
        valid_until=datetime(2027, 2, 20),
        status="active",
    )
    order = Order(customer=customer, customer_contract=contract_a, status=OrderStatus.NEGOTIATION)
    db.add_all([customer, contract_a, contract_b, order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(contract_a)
    await db.refresh(contract_b)

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {"file_id": "fake-act-open-contract", "edit_url": "https://docs.google.com/document/d/fake-act-open-contract/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/act",
        params={"contract_date": "2026-05-23T00:00:00", "base_document_id": 0},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["base_customer_contract_id"] == contract_a.id
    assert captured["replacements"]["{{base_document_number}}"] == "ОД-2026-А"
    assert captured["replacements"]["{{base_document_date}}"] == "15.01.2026"

    result = await db.execute(select(OrderDocument).where(OrderDocument.doc_type == "act"))
    act_doc = result.scalars().first()
    assert act_doc.base_customer_contract_id == contract_a.id
    order_id = order.id
    customer_id = customer.id
    contract_a_id = contract_a.id
    contract_b_id = contract_b.id
    act_doc_id = act_doc.id
    act_doc_number = act_doc.number
    act_doc_date = act_doc.date
    act_base_customer_contract_id = act_doc.base_customer_contract_id

    order.customer_contract_id = contract_b_id
    db.add(order)
    await db.commit()
    db.expire_all()

    docs_response = await async_client.get(f"/api/manager/orders/{order_id}/documents", headers=headers)
    assert docs_response.status_code == 200
    act_item = next(item for item in docs_response.json()["items"] if item["id"] == act_doc_id)
    assert act_item["base_customer_contract_id"] == contract_a_id
    assert act_item["base_document_type"] == "contract"
    assert act_item["base_document_type_label"] == "Договор"
    assert act_item["base_document_number"] == "ОД-2026-А"
    assert act_item["base_document_date"].startswith("2026-01-15")

    detail_response = await async_client.get(f"/api/manager/orders/{order_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_act_item = next(item for item in detail_response.json()["documents"] if item["id"] == act_doc_id)
    assert detail_act_item["base_customer_contract_id"] == contract_a_id
    assert detail_act_item["base_document_type"] == "contract"
    assert detail_act_item["base_document_type_label"] == "Договор"
    assert detail_act_item["base_document_number"] == "ОД-2026-А"
    assert detail_act_item["base_document_date"].startswith("2026-01-15")

    customer_docs_response = await async_client.get(f"/api/manager/customers/{customer_id}/docs", headers=headers)
    assert customer_docs_response.status_code == 200
    customer_act_item = next(item for item in customer_docs_response.json()["items"] if item["id"] == act_doc_id)
    assert customer_act_item["base_customer_contract_id"] == contract_a_id
    assert customer_act_item["base_document_type"] == "contract"
    assert customer_act_item["base_document_type_label"] == "Договор"
    assert customer_act_item["base_document_number"] == "ОД-2026-А"
    assert customer_act_item["base_document_date"].startswith("2026-01-15")

    from services.documents.standard import ActStrategy

    strategy = ActStrategy(db, order_id)
    await strategy.fetch_order()
    base_contract = await db.get(CustomerContract, act_base_customer_contract_id)
    replacements_after_switch = await strategy._prepare_base_variables(
        doc_number=act_doc_number,
        doc_type="act",
        document_date=act_doc_date,
        base_customer_contract=base_contract,
    )
    assert replacements_after_switch["{{base_document_number}}"] == "ОД-2026-А"
    assert replacements_after_switch["{{contract_number}}"] == "ОД-2026-А"


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
        additional_conditions="- Работы выполнять после согласования с администратором.",
        technical_meta={
            "equipment_serial_number": "SN-001",
            "equipment_inventory_number": "INV-777",
            "technical_condition": "Компрессор отключается по защите.",
            "technical_conclusion": "Компрессор подлежит замене.",
            "recommended_decision": "Вывести из эксплуатации.",
            "repair": {
                "repair_status": "awaiting_customer_approval",
                "customer_approval_status": "pending",
                "customer_approval_note": "Ожидается согласование сметы.",
                "parts_status": "awaiting",
                "parts_note": "Требуется заказать компрессор.",
                "repair_completion_note": "Завершение после согласования и поставки.",
                "refrigerant_type": "R410A",
                "refrigerant_amount": "0,60 кг",
                "refrigerant_pricing_mode": "по фактической массе",
                "repair_not_viable": "Да",
                "repair_not_viable_reason": "Стоимость ремонта сопоставима с заменой оборудования.",
            },
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
    assert replacements["{{repair_status}}"] == "awaiting_customer_approval"
    assert replacements["{{customer_approval_status}}"] == "pending"
    assert replacements["{{customer_approval_note}}"] == "Ожидается согласование сметы."
    assert replacements["{{parts_status}}"] == "awaiting"
    assert replacements["{{parts_note}}"] == "Требуется заказать компрессор."
    assert replacements["{{repair_completion_note}}"] == "Завершение после согласования и поставки."
    assert replacements["{{refrigerant_type}}"] == "R410A"
    assert replacements["{{refrigerant_amount}}"] == "0,60 кг"
    assert replacements["{{refrigerant_pricing_mode}}"] == "по фактической массе"
    assert replacements["{{repair_not_viable}}"] == "Да"
    assert replacements["{{repair_not_viable_reason}}"] == "Стоимость ремонта сопоставима с заменой оборудования."
    assert replacements["{{additional_conditions}}"] == "Работы выполнять после согласования с администратором."


@pytest.mark.asyncio
async def test_manager_order_generate_defect_act_from_structured_repair_meta(async_client, db, monkeypatch):
    customer = Customer(name='ООО "Структура"', phone="+375297777700", type=CustomerType.company)
    order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEW_LEAD,
        technical_meta={
            "repair": {
                "customer_complaint": "Плохо охлаждает",
                "fault_type": "refrigerant_leak",
                "diagnostic_notes": "Обмерзает теплообменник внутреннего блока.",
                "structured_diagnosis": {
                    "fault_type": "refrigerant_leak",
                    "fault_location": "flare_connections",
                    "repairable": True,
                    "operation_status": "limited",
                    "risks": ["compressor_damage"],
                    "recommended_actions": ["restore_circuit_tightness", "vacuuming", "full_refrigerant_charge"],
                    "refrigerant": "R410A",
                    "refrigerant_amount": "790 g",
                    "hidden_defects_possible": True,
                },
            },
        },
    )
    db.add_all([customer, order])
    await db.commit()
    await db.refresh(order)

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {"file_id": "fake-defect-act", "edit_url": "https://docs.google.com/document/d/fake-defect-act/edit"}

        def replace_placeholders(self, file_id, replacements):
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
    assert replacements["{{technical_condition}}"].startswith("Неисправен. Выявлены признаки утечки хладагента")
    assert replacements["{{measurement_result}}"].startswith("Выявлены признаки утечки хладагента")
    assert "манометрическая диагностика" in replacements["{{inspection_work_done}}"]
    assert "Обмерзает теплообменник" not in replacements["{{measurement_result}}"]
    assert "Эксплуатация оборудования допускается только с ограничениями" in replacements["{{further_use_assessment}}"]
    assert "повреждению компрессора" in replacements["{{operation_restrictions}}"]
    assert "восстановить герметичность холодильного контура" in replacements["{{technical_conclusion}}"]
    assert replacements["{{repair_possible}}"] == "Да"
    assert replacements["{{refrigerant_type}}"] == "R410A"
    assert replacements["{{refrigerant_amount}}"] == "790 g"


@pytest.mark.asyncio
async def test_manager_order_generate_document_applies_draft_conditions_atomically(async_client, db, monkeypatch):
    customer = Customer(name="ООО Атом", phone="+375291010101", type=CustomerType.company)
    product = Product(title="Кондиционер Atom", slug="atom-ac", price=1000)
    order = Order(customer=customer, status=OrderStatus.NEW_LEAD)
    db.add_all([customer, product, order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(product)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
    await db.commit()

    captured = {}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            return {"file_id": "fake-atomic-defect-act", "edit_url": "https://docs.google.com/document/d/fake/edit"}

        def replace_placeholders(self, file_id, replacements):
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/defect_act",
        headers=headers,
        json={"additional_conditions": "  Работы только после допуска.  "},
    )

    assert response.status_code == 200, response.text
    assert captured["replacements"]["{{additional_conditions}}"] == "Работы только после допуска."
    await db.refresh(order)
    assert order.additional_conditions == "Работы только после допуска."


@pytest.mark.asyncio
async def test_manager_order_generate_document_with_draft_conditions_recreates_existing_singleton(async_client, db, monkeypatch):
    customer = Customer(name="ООО Повтор", phone="+375291010103", type=CustomerType.company)
    product = Product(title="Кондиционер Repeat", slug="repeat-ac", price=1000)
    order = Order(customer=customer, status=OrderStatus.NEW_LEAD, additional_conditions="Старые условия")
    db.add_all([customer, product, order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(product)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
    await db.commit()

    existing_doc = OrderDocument(
        order_id=order.id,
        doc_type="defect_act",
        number="ДА-2026-001",
        google_file_id="old-defect-act",
        google_edit_url="https://docs.google.com/document/d/old-defect-act/edit",
    )
    db.add(existing_doc)
    await db.commit()
    await db.refresh(existing_doc)

    captured = {"copies": 0}

    class _FakeGoogleService:
        def copy_template(self, template_id, title):
            captured["copies"] += 1
            return {
                "file_id": f"fake-repeat-defect-act-{captured['copies']}",
                "edit_url": f"https://docs.google.com/document/d/fake-repeat-defect-act-{captured['copies']}/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            captured["replacements"] = replacements

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FakeGoogleService())

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/orders/{order.id}/documents/defect_act",
        headers=headers,
        json={"additional_conditions": "Новые условия для нового документа"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["doc_id"] != existing_doc.id
    assert captured["copies"] == 1
    assert captured["replacements"]["{{additional_conditions}}"] == "Новые условия для нового документа"
    await db.refresh(order)
    assert order.additional_conditions == "Новые условия для нового документа"


@pytest.mark.asyncio
async def test_manager_order_generate_document_rolls_back_draft_conditions_on_failure(db_engine, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    from core.database import get_session
    from main import app

    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    customer = Customer(name="ООО Rollback", phone="+375291010102", type=CustomerType.company)
    product = Product(title="Кондиционер Rollback", slug="rollback-ac", price=1000)
    order = Order(customer=customer, status=OrderStatus.NEW_LEAD, additional_conditions="Старые условия")
    async with session_factory() as setup_session:
        setup_session.add_all([customer, product, order])
        await setup_session.commit()
        await setup_session.refresh(order)
        await setup_session.refresh(product)

        setup_session.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
        await setup_session.commit()
        order_id = order.id

    class _FailingGoogleService:
        def copy_template(self, template_id, title):
            raise RuntimeError("google unavailable")

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: _FailingGoogleService())

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await _auth_headers(client)
            response = await client.post(
                f"/api/manager/orders/{order_id}/documents/defect_act",
                headers=headers,
                json={"additional_conditions": "Новые условия не должны сохраниться"},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    async with session_factory() as verify_session:
        fresh_order = await verify_session.get(Order, order_id)
        assert fresh_order is not None
        assert fresh_order.additional_conditions == "Старые условия"


@pytest.mark.asyncio
async def test_manager_order_generate_document_cleans_google_file_after_replace_failure(db_engine, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    from core.database import get_session
    from main import app

    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    customer = Customer(name="ООО Cleanup", phone="+375291010104", type=CustomerType.company)
    product = Product(title="Кондиционер Cleanup", slug="cleanup-ac", price=1000)
    order = Order(customer=customer, status=OrderStatus.NEW_LEAD, additional_conditions="Старые условия")
    async with session_factory() as setup_session:
        setup_session.add_all([customer, product, order])
        await setup_session.commit()
        await setup_session.refresh(order)
        await setup_session.refresh(product)

        setup_session.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000, cost=700))
        await setup_session.commit()
        order_id = order.id

    class _FailingAfterCopyGoogleService:
        def __init__(self):
            self.deleted_files = []

        def copy_template(self, template_id, title):
            return {"file_id": "orphan-candidate", "edit_url": "https://docs.google.com/document/d/orphan-candidate/edit"}

        def replace_placeholders(self, file_id, replacements):
            raise RuntimeError("replace failed")

        def delete_file(self, file_id):
            self.deleted_files.append(file_id)

    google_service = _FailingAfterCopyGoogleService()

    from services import document_service

    monkeypatch.setattr(document_service, "get_google_service", lambda: google_service)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await _auth_headers(client)
            response = await client.post(
                f"/api/manager/orders/{order_id}/documents/defect_act",
                headers=headers,
                json={"additional_conditions": "Новые условия не должны сохраниться"},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    assert google_service.deleted_files == ["orphan-candidate"]
    async with session_factory() as verify_session:
        fresh_order = await verify_session.get(Order, order_id)
        assert fresh_order is not None
        assert fresh_order.additional_conditions == "Старые условия"
        docs = (
            await verify_session.execute(select(OrderDocument).where(OrderDocument.order_id == order_id))
        ).scalars().all()
        assert docs == []


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
async def test_manager_doc_delete_blocks_base_document_with_dependents(async_client, db, monkeypatch):
    customer = Customer(name="DocBaseGuard", phone="+375290000001", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    from models import OrderDocument
    base_doc = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="I-BASE",
        google_file_id="fid_base",
        google_edit_url="http://edit_base",
    )
    db.add(base_doc)
    await db.flush()
    dependent_doc = OrderDocument(
        order_id=order.id,
        doc_type="act",
        number="A-DEP",
        base_document_id=base_doc.id,
        google_file_id="fid_dep",
        google_edit_url="http://edit_dep",
    )
    db.add(dependent_doc)
    await db.commit()
    await db.refresh(base_doc)
    await db.refresh(dependent_doc)

    from services.google_service import get_google_service
    deleted_ids = []

    def _fake_delete_file(file_id):
        deleted_ids.append(file_id)

    monkeypatch.setattr(get_google_service(), "delete_file", _fake_delete_file)

    headers = await _auth_headers(async_client)
    resp = await async_client.delete(f"/api/manager/docs/{base_doc.id}", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "document_has_dependents"
    assert deleted_ids == []

    from sqlmodel import select

    base_res = await db.execute(select(OrderDocument).where(OrderDocument.id == base_doc.id))
    dep_res = await db.execute(select(OrderDocument).where(OrderDocument.id == dependent_doc.id))

    assert base_res.scalar_one_or_none() is not None
    assert dep_res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_manager_order_delete_cascades_related_entities(async_client, db, monkeypatch):
    customer = Customer(name="Delete Order", phone="+375290001234", type=CustomerType.individual)
    product = Product(title="Delete Product", slug="delete-product", price=4000, specs={"area_m2": 35})
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
