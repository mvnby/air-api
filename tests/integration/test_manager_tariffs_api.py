import pytest

from core.config import settings
from models import ServiceTariff


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

    create_rule_payload = {
        "rule_type": "per_meter_over_included",
        "name": "Доп. трасса",
        "line_template": "доп. трасса {qty} м",
        "unit": "м",
        "unit_price": 45,
        "is_optional": False,
        "is_favorite": True,
        "is_active": True,
        "sort_order": 5,
    }
    create_rule_resp = await async_client.post(
        f"/api/manager/tariffs/{tariff_id}/rules",
        headers=headers,
        json=create_rule_payload,
    )
    assert create_rule_resp.status_code == 201
    rule = create_rule_resp.json()
    assert rule["tariff_id"] == tariff_id
    assert rule["is_favorite"] is True
    rule_id = rule["id"]

    duplicate_rule_resp = await async_client.post(
        f"/api/manager/tariffs/{tariff_id}/rules",
        headers=headers,
        json=create_rule_payload,
    )
    assert duplicate_rule_resp.status_code == 201
    assert duplicate_rule_resp.json()["id"] == rule_id

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
        json={"unit_price": 50, "is_favorite": False},
    )
    assert update_rule_resp.status_code == 200
    assert update_rule_resp.json()["unit_price"] == 50
    assert update_rule_resp.json()["is_favorite"] is False

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


@pytest.mark.asyncio
async def test_manager_quick_tariffs_search_active_only(async_client, db):
    active = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера",
        estimate_template="Монтаж кондиционера, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
        sort_order=10,
    )
    inactive = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж архивный",
        estimate_template="Монтаж архивный",
        category="Wall",
        power_range="12",
        base_price=1,
        included_route_meters=3,
        is_active=False,
        sort_order=1,
    )
    maintenance = ServiceTariff(
        service_kind="maintenance",
        selector_label="Обслуживание бытового кондиционера",
        estimate_template="Обслуживание бытового кондиционера",
        category="maintenance",
        power_range="12",
        base_price=120,
        included_route_meters=0,
        is_active=True,
        sort_order=5,
    )
    dismantling = ServiceTariff(
        service_kind="dismantling",
        selector_label="Демонтаж настенного кондиционера",
        estimate_template="Демонтаж настенного кондиционера",
        category="Wall",
        power_range="12",
        base_price=100,
        included_route_meters=0,
        is_active=True,
        sort_order=1,
    )
    db.add(active)
    db.add(inactive)
    db.add(maintenance)
    db.add(dismantling)
    await db.commit()
    await db.refresh(active)
    await db.refresh(maintenance)
    await db.refresh(dismantling)

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/tariffs/quick-add?q=монт&service_kind=installation&limit=10",
        headers=headers,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["tariff_id"] == active.id
    assert items[0]["price"] == 500
    assert items[0]["title"] == "Монтаж настенного кондиционера, мощностью до 3,5 кВт, включая трассу длиной до 3 м"

    all_kinds_resp = await async_client.get(
        "/api/manager/tariffs/quick-add?q=монт&limit=10",
        headers=headers,
    )
    assert all_kinds_resp.status_code == 200
    all_kinds_items = all_kinds_resp.json()["items"]
    assert [item["tariff_id"] for item in all_kinds_items[:2]] == [active.id, dismantling.id]


@pytest.mark.asyncio
async def test_manager_tariffs_accept_repair_direction(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/tariffs",
        headers=headers,
        json={
            "service_kind": "repair",
            "selector_label": "Ремонт кондиционера",
            "estimate_template": "Ремонт кондиционера",
            "category": "repair",
            "power_range": "бытовой",
            "base_price": 150,
            "included_route_meters": 3,
            "is_active": True,
            "sort_order": 5,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["service_kind"] == "repair"
    assert created["included_route_meters"] == 0

    list_resp = await async_client.get(
        "/api/manager/tariffs?service_kind=repair",
        headers=headers,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["id"] == created["id"] for item in items)

    quick_resp = await async_client.get(
        "/api/manager/tariffs/quick-add?q=ремонт&service_kind=repair",
        headers=headers,
    )
    assert quick_resp.status_code == 200
    quick_items = quick_resp.json()["items"]
    assert len(quick_items) == 1
    assert quick_items[0]["service_kind"] == "repair"
    assert quick_items[0]["title"] == "Ремонт кондиционера"


@pytest.mark.asyncio
async def test_manager_tariffs_accept_pre_install_direction_with_route(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/tariffs",
        headers=headers,
        json={
            "service_kind": "pre_install",
            "selector_label": "Закладка коммуникаций под кондиционер",
            "estimate_template": "Закладка межблочной трассы под кондиционер, включая материалы",
            "category": "Wall",
            "power_range": "07-12",
            "base_price": 500,
            "included_route_meters": 3,
            "is_active": True,
            "sort_order": 5,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["service_kind"] == "pre_install"
    assert created["included_route_meters"] == 3

    rule_resp = await async_client.post(
        f"/api/manager/tariffs/{created['id']}/rules",
        headers=headers,
        json={
            "rule_type": "per_meter_over_included",
            "name": "Дополнительная трасса сверх 3 м",
            "line_template": "дополнительная трасса {qty} м",
            "unit": "м",
            "unit_price": 50,
            "is_optional": False,
            "is_active": True,
            "sort_order": 10,
        },
    )
    assert rule_resp.status_code == 201

    quick_resp = await async_client.get(
        "/api/manager/tariffs/quick-add?q=заклад&service_kind=pre_install",
        headers=headers,
    )
    assert quick_resp.status_code == 200
    quick_items = quick_resp.json()["items"]
    assert len(quick_items) == 1
    assert quick_items[0]["service_kind"] == "pre_install"
    assert "трассу длиной до 3 м" in quick_items[0]["title"]


@pytest.mark.asyncio
async def test_manager_favorite_tariff_rules_by_direction(async_client):
    headers = await _auth_headers(async_client)

    source_tariff_resp = await async_client.post(
        "/api/manager/tariffs",
        headers=headers,
        json={
            "service_kind": "repair",
            "selector_label": "Ремонт бытовой",
            "estimate_template": "Ремонт кондиционера",
            "category": "repair",
            "power_range": "",
            "base_price": 100,
            "included_route_meters": 0,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert source_tariff_resp.status_code == 201
    source_tariff_id = source_tariff_resp.json()["id"]

    other_tariff_resp = await async_client.post(
        "/api/manager/tariffs",
        headers=headers,
        json={
            "service_kind": "repair",
            "selector_label": "Ремонт полупром",
            "estimate_template": "Ремонт полупромышленного кондиционера",
            "category": "repair",
            "power_range": "до 17 кВт",
            "base_price": 200,
            "included_route_meters": 0,
            "is_active": True,
            "sort_order": 2,
        },
    )
    assert other_tariff_resp.status_code == 201
    other_tariff_id = other_tariff_resp.json()["id"]

    favorite_rule_resp = await async_client.post(
        f"/api/manager/tariffs/{source_tariff_id}/rules",
        headers=headers,
        json={
            "rule_type": "per_unit_manual",
            "name": "Заправка хладагентом",
            "line_template": "{name} ({qty} {unit})",
            "unit": "кг",
            "unit_price": 60,
            "is_optional": True,
            "is_favorite": True,
            "is_active": True,
            "sort_order": 10,
        },
    )
    assert favorite_rule_resp.status_code == 201
    favorite_rule = favorite_rule_resp.json()

    favorite_list_resp = await async_client.get(
        f"/api/manager/tariffs/rules/favorites?service_kind=repair&exclude_tariff_id={other_tariff_id}",
        headers=headers,
    )
    assert favorite_list_resp.status_code == 200
    items = favorite_list_resp.json()["items"]
    assert [item["id"] for item in items] == [favorite_rule["id"]]
    assert items[0]["name"] == "Заправка хладагентом"

    excluded_list_resp = await async_client.get(
        f"/api/manager/tariffs/rules/favorites?service_kind=repair&exclude_tariff_id={source_tariff_id}",
        headers=headers,
    )
    assert excluded_list_resp.status_code == 200
    assert excluded_list_resp.json()["items"] == []
