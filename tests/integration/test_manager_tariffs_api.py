import pytest

from core.config import settings


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_tariffs_and_rules_crud(async_client):
    headers = await _auth_headers(async_client)

    create_tariff_resp = await async_client.post(
        "/api/manager/tariffs",
        headers=headers,
        json={
            "service_kind": "installation",
            "selector_label": "Монтаж настенного до 3.5 кВт",
            "estimate_template": "Монтаж сплит-системы настенного типа, включая расходные материалы",
            "category": "Wall",
            "power_range": "12",
            "base_price": 500,
            "included_route_meters": 3,
            "is_active": True,
            "sort_order": 10,
        },
    )
    assert create_tariff_resp.status_code == 201
    tariff = create_tariff_resp.json()
    assert tariff["selector_label"].startswith("Монтаж")

    tariff_id = tariff["id"]

    create_rule_resp = await async_client.post(
        f"/api/manager/tariffs/{tariff_id}/rules",
        headers=headers,
        json={
            "rule_type": "per_meter_over_included",
            "name": "Доп. трасса",
            "line_template": "доп. трасса {qty} м",
            "unit": "м",
            "unit_price": 45,
            "is_optional": False,
            "is_active": True,
            "sort_order": 5,
        },
    )
    assert create_rule_resp.status_code == 201
    rule = create_rule_resp.json()
    assert rule["tariff_id"] == tariff_id
    rule_id = rule["id"]

    list_tariffs_resp = await async_client.get(
        "/api/manager/tariffs?service_kind=installation",
        headers=headers,
    )
    assert list_tariffs_resp.status_code == 200
    items = list_tariffs_resp.json()["items"]
    assert any(item["id"] == tariff_id for item in items)

    list_rules_resp = await async_client.get(
        f"/api/manager/tariffs/{tariff_id}/rules",
        headers=headers,
    )
    assert list_rules_resp.status_code == 200
    assert len(list_rules_resp.json()["items"]) == 1

    update_rule_resp = await async_client.put(
        f"/api/manager/tariffs/{tariff_id}/rules/{rule_id}",
        headers=headers,
        json={"unit_price": 50},
    )
    assert update_rule_resp.status_code == 200
    assert update_rule_resp.json()["unit_price"] == 50

    delete_rule_resp = await async_client.delete(
        f"/api/manager/tariffs/{tariff_id}/rules/{rule_id}",
        headers=headers,
    )
    assert delete_rule_resp.status_code == 200

    delete_tariff_resp = await async_client.delete(
        f"/api/manager/tariffs/{tariff_id}",
        headers=headers,
    )
    assert delete_tariff_resp.status_code == 200
