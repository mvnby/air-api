import pytest
from datetime import datetime
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerBranch, CustomerType, EquipmentServiceHistory, Order, OrderStatus


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_equipment_create_list_detail_and_history_ordering(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(name="HVAC Owner", phone="+375291110101", type=CustomerType.company, inn="100200300")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    branch = CustomerBranch(
        customer_id=customer.id,
        name="Серверная",
        delivery_address="Минск, Машерова 1",
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    create_resp = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer.id,
            "customer_branch_id": branch.id,
            "equipment_type": "vrf",
            "display_name": "VRF серверной",
            "brand": "Daikin",
            "model": "RXQ",
            "serial": "SN-100",
            "inventory_number": "INV-9",
            "location_hint": "стойка A",
            "refrigerant_type": "R410A",
            "notes": "Критичная зона",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    equipment = create_resp.json()
    equipment_id = equipment["id"]
    assert equipment["customer_id"] == customer.id
    assert equipment["customer_branch_id"] == branch.id
    assert equipment["display_name"] == "VRF серверной"
    assert equipment["refrigerant_type"] == "R410A"

    older_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={
            "event_type": "diagnostic",
            "event_date": "2026-01-10T09:00:00",
            "complaint_snapshot": "Не охлаждает",
            "diagnostic_result": "Недостаток хладагента.",
            "repair_recommendation": "Проверить контур на утечку.",
            "refrigerant_type": "R410A",
            "refrigerant_amount": "0,40 кг",
        },
    )
    assert older_resp.status_code == 201, older_resp.text

    newer_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={
            "event_type": "not_repairable",
            "event_date": "2026-02-10T09:00:00",
            "diagnostic_result": "Компрессор отключается по защите.",
            "not_repairable": True,
            "not_repairable_reason": "Ремонт экономически нецелесообразен.",
            "notes": "Рекомендована замена.",
        },
    )
    assert newer_resp.status_code == 201, newer_resp.text
    newer = newer_resp.json()
    assert newer["event_type"] == "not_repairable"
    assert newer["not_repairable"] is True
    assert newer["not_repairable_reason"] == "Ремонт экономически нецелесообразен."

    list_resp = await async_client.get(
        f"/api/manager/equipment?customer_id={customer.id}&customer_branch_id={branch.id}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()["items"]] == [equipment_id]

    history_resp = await async_client.get(f"/api/manager/equipment/{equipment_id}/history", headers=headers)
    assert history_resp.status_code == 200
    history_items = history_resp.json()["items"]
    assert [item["event_type"] for item in history_items] == ["not_repairable", "diagnostic"]
    assert history_items[1]["refrigerant_type"] == "R410A"
    assert history_items[1]["refrigerant_amount"] == "0,40 кг"

    detail_resp = await async_client.get(f"/api/manager/equipment/{equipment_id}?history_limit=1", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == equipment_id
    assert len(detail["recent_history"]) == 1
    assert detail["recent_history"][0]["event_type"] == "not_repairable"


@pytest.mark.asyncio
async def test_manager_equipment_history_from_repair_order_maps_meta_and_allows_unassigned_branch(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(name="Repair Owner", phone="+375291110102", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    branch = CustomerBranch(
        customer_id=customer.id,
        name="Офис",
        delivery_address="Минск, Победителей 10",
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    equipment_resp = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer.id,
            "customer_branch_id": branch.id,
            "equipment_type": "split",
            "brand": "Mitsubishi",
            "model": "MSZ",
            "serial": "SN-REPAIR-1",
        },
    )
    assert equipment_resp.status_code == 201, equipment_resp.text
    equipment_id = equipment_resp.json()["id"]

    order = Order(
        customer_id=customer.id,
        customer_branch_id=None,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        updated_at=datetime(2026, 3, 1, 12, 0, 0),
        technical_meta={
            "repair": {
                "repair_status": "completed",
                "customer_complaint": "Плохо холодит",
                "diagnostic_result": "Выявлена утечка хладагента.",
                "repair_recommendation": "Устранить утечку и дозаправить контур.",
                "refrigerant_type": "R32",
                "refrigerant_amount": "0,35 кг",
                "repair_completion_note": "Ремонт завершен.",
            }
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    history_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history/from-repair-order",
        headers=headers,
        json={"order_id": order.id},
    )
    assert history_resp.status_code == 201, history_resp.text
    history = history_resp.json()
    assert history["order_id"] == order.id
    assert history["event_type"] == "repair"
    assert history["complaint_snapshot"] == "Плохо холодит"
    assert history["diagnostic_result"] == "Выявлена утечка хладагента."
    assert history["repair_recommendation"] == "Устранить утечку и дозаправить контур."
    assert history["refrigerant_type"] == "R32"
    assert history["refrigerant_amount"] == "0,35 кг"
    assert history["notes"] == "Ремонт завершен."


@pytest.mark.asyncio
async def test_manager_equipment_ownership_guards_reject_cross_customer_and_branch_mismatch(async_client, db):
    headers = await _auth_headers(async_client)
    customer_a = Customer(name="Owner A", phone="+375291110103", type=CustomerType.company)
    customer_b = Customer(name="Owner B", phone="+375291110104", type=CustomerType.company)
    db.add(customer_a)
    db.add(customer_b)
    await db.commit()
    await db.refresh(customer_a)
    await db.refresh(customer_b)
    branch_a = CustomerBranch(customer_id=customer_a.id, name="A1", delivery_address="Минск, A1")
    branch_a_other = CustomerBranch(customer_id=customer_a.id, name="A2", delivery_address="Минск, A2")
    branch_b = CustomerBranch(customer_id=customer_b.id, name="B1", delivery_address="Минск, B1")
    db.add(branch_a)
    db.add(branch_a_other)
    db.add(branch_b)
    await db.commit()
    await db.refresh(branch_a)
    await db.refresh(branch_a_other)
    await db.refresh(branch_b)

    wrong_branch_resp = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer_a.id,
            "customer_branch_id": branch_b.id,
            "equipment_type": "split",
        },
    )
    assert wrong_branch_resp.status_code == 400
    assert "Customer branch does not belong" in wrong_branch_resp.text

    equipment_resp = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={
            "customer_id": customer_a.id,
            "customer_branch_id": branch_a.id,
            "equipment_type": "split",
            "display_name": "Split A1",
        },
    )
    assert equipment_resp.status_code == 201, equipment_resp.text
    equipment_id = equipment_resp.json()["id"]

    cross_customer_order = Order(
        customer_id=customer_b.id,
        customer_branch_id=branch_b.id,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        technical_meta={"repair": {"repair_status": "completed", "customer_complaint": "Не холодит"}},
    )
    unknown_customer_order = Order(
        customer_id=None,
        customer_branch_id=None,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        technical_meta={"repair": {"repair_status": "completed", "customer_complaint": "Не холодит"}},
    )
    branch_mismatch_order = Order(
        customer_id=customer_a.id,
        customer_branch_id=branch_a_other.id,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        technical_meta={"repair": {"repair_status": "completed", "customer_complaint": "Не холодит"}},
    )
    db.add(cross_customer_order)
    db.add(unknown_customer_order)
    db.add(branch_mismatch_order)
    await db.commit()
    await db.refresh(cross_customer_order)
    await db.refresh(unknown_customer_order)
    await db.refresh(branch_mismatch_order)

    direct_cross_customer_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={
            "order_id": cross_customer_order.id,
            "event_type": "repair",
            "event_date": "2026-03-10T09:00:00",
            "notes": "Чужой заказ",
        },
    )
    assert direct_cross_customer_resp.status_code == 400
    assert "Order customer does not match" in direct_cross_customer_resp.text

    direct_unknown_customer_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history",
        headers=headers,
        json={
            "order_id": unknown_customer_order.id,
            "event_type": "repair",
            "event_date": "2026-03-10T10:00:00",
            "notes": "Заказ без владельца",
        },
    )
    assert direct_unknown_customer_resp.status_code == 400
    assert "Order customer is required" in direct_unknown_customer_resp.text

    from_order_cross_customer_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history/from-repair-order",
        headers=headers,
        json={"order_id": cross_customer_order.id},
    )
    assert from_order_cross_customer_resp.status_code == 400
    assert "Order customer does not match" in from_order_cross_customer_resp.text

    from_order_unknown_customer_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history/from-repair-order",
        headers=headers,
        json={"order_id": unknown_customer_order.id},
    )
    assert from_order_unknown_customer_resp.status_code == 400
    assert "Order customer is required" in from_order_unknown_customer_resp.text

    branch_mismatch_resp = await async_client.post(
        f"/api/manager/equipment/{equipment_id}/history/from-repair-order",
        headers=headers,
        json={"order_id": branch_mismatch_order.id},
    )
    assert branch_mismatch_resp.status_code == 400
    assert "Order branch does not match" in branch_mismatch_resp.text

    history_result = await db.execute(select(EquipmentServiceHistory).where(EquipmentServiceHistory.equipment_id == equipment_id))
    assert history_result.scalars().all() == []
