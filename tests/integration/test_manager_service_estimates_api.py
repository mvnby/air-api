import pytest

from core.config import settings
from models import Customer, ServiceTariff, ServiceTariffRule


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_service_estimates_calculate_and_snapshot_flow(async_client, db):
    headers = await _auth_headers(async_client)

    customer = Customer(tenant_id=1, name="ООО Тест", phone="+375291112233")
    tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного до 3.5 кВт",
        estimate_template="Монтаж сплит-системы настенного типа, включая расходные материалы",
        short_name="Монтаж настенного до 3.5 кВт",
        full_description="Монтаж сплит-системы настенного типа, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3.0,
    )
    db.add(customer)
    db.add(tariff)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(tariff)

    meter_rule = ServiceTariffRule(
        tariff_id=tariff.id,
        rule_type="per_meter_over_included",
        name="Доп. трасса",
        line_template="трасса {qty} м",
        unit="м",
        unit_price=40,
        is_optional=False,
        is_active=True,
        sort_order=10,
    )
    holes_rule = ServiceTariffRule(
        tariff_id=tariff.id,
        rule_type="per_hole_manual",
        name="Доп. отверстия",
        line_template="{extra_holes_count} доп. отверстий",
        unit="шт",
        unit_price=50,
        is_optional=False,
        is_active=True,
        sort_order=20,
    )
    per_unit_rule = ServiceTariffRule(
        tariff_id=tariff.id,
        rule_type="per_unit_manual",
        name="Штробление",
        line_template="{name} ({qty} {unit})",
        unit="шт",
        unit_price=60,
        is_optional=True,
        is_active=True,
        sort_order=30,
    )
    db.add(meter_rule)
    db.add(holes_rule)
    db.add(per_unit_rule)
    await db.commit()
    await db.refresh(per_unit_rule)

    calculate_payload = {
        "tariff_id": tariff.id,
        "route_length_m": 7,
        "quantity": 1,
        "extra_holes_count": 1,
        "rule_inputs": [{"rule_id": per_unit_rule.id, "qty": 2}],
        "discount_amount": 30,
    }
    calculate_resp = await async_client.post(
        "/api/manager/service-estimates/calculate",
        json=calculate_payload,
        headers=headers,
    )
    assert calculate_resp.status_code == 200
    calculate_data = calculate_resp.json()
    assert calculate_data["subtotal"] == 830
    assert calculate_data["total"] == 800
    assert len(calculate_data["lines"]) == 4
    assert calculate_data["tariff"]["id"] == tariff.id

    create_payload = {
        **calculate_payload,
        "title": "Смета API",
        "comment": "Тестовый snapshot",
        "customer_id": customer.id,
    }
    create_resp = await async_client.post(
        "/api/manager/service-estimates",
        json=create_payload,
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["title"] == "Смета API"
    assert created["total"] == 800
    assert len(created["lines"]) == 4

    detail_resp = await async_client.get(
        f"/api/manager/service-estimates/{created['id']}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == created["id"]
    assert detail_resp.json()["customer_id"] == customer.id
    assert detail_resp.json()["tariff"]["id"] == tariff.id

    order_lines_detailed_resp = await async_client.get(
        f"/api/manager/service-estimates/{created['id']}/order-lines?mode=detailed",
        headers=headers,
    )
    assert order_lines_detailed_resp.status_code == 200
    detailed_data = order_lines_detailed_resp.json()
    assert detailed_data["mode"] == "detailed"
    assert detailed_data["description_mode"] == "short"
    assert len(detailed_data["services"]) == 4
    assert detailed_data["services"][0]["title"] == "Монтаж настенного до 3.5 кВт"

    order_lines_full_resp = await async_client.get(
        f"/api/manager/service-estimates/{created['id']}/order-lines?mode=detailed&description_mode=full",
        headers=headers,
    )
    assert order_lines_full_resp.status_code == 200
    full_data = order_lines_full_resp.json()
    assert full_data["description_mode"] == "full"
    assert full_data["services"][0]["title"].startswith("Монтаж сплит-системы")

    order_lines_collapsed_resp = await async_client.get(
        f"/api/manager/service-estimates/{created['id']}/order-lines?mode=collapsed&description_mode=full",
        headers=headers,
    )
    assert order_lines_collapsed_resp.status_code == 200
    collapsed_data = order_lines_collapsed_resp.json()
    assert collapsed_data["mode"] == "collapsed"
    assert collapsed_data["description_mode"] == "full"
    assert len(collapsed_data["services"]) == 1
    assert collapsed_data["services"][0]["price"] == 800

    list_resp = await async_client.get(
        "/api/manager/service-estimates?page=1&limit=20",
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    filtered_list_resp = await async_client.get(
        f"/api/manager/service-estimates?page=1&limit=20&customer_id={customer.id}",
        headers=headers,
    )
    assert filtered_list_resp.status_code == 200
    filtered_list = filtered_list_resp.json()
    assert filtered_list["total"] == 1
    assert filtered_list["items"][0]["customer_id"] == customer.id

    delete_resp = await async_client.delete(
        f"/api/manager/service-estimates/{created['id']}",
        headers=headers,
    )
    assert delete_resp.status_code == 200

    list_after_delete_resp = await async_client.get(
        "/api/manager/service-estimates?page=1&limit=20",
        headers=headers,
    )
    assert list_after_delete_resp.status_code == 200
    assert list_after_delete_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_manager_service_estimates_requires_auth(async_client):
    resp = await async_client.post(
        "/api/manager/service-estimates/calculate",
        json={"tariff_id": 1, "route_length_m": 3, "quantity": 1},
    )
    assert resp.status_code == 401
