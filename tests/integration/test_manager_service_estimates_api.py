import pytest

from core.config import settings
from models import InstallationRate, Service


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

    tariff = InstallationRate(
        category="Wall",
        power_range="12",
        base_price=500,
        extra_pipe_price=40,
        included_pipe_meters=3,
        is_fixed=True,
    )
    addon_service = Service(
        title="Штробление",
        slug="chasing-work",
        category="installation_option",
        base_price=60,
        is_active=True,
    )
    db.add(tariff)
    db.add(addon_service)
    await db.commit()
    await db.refresh(tariff)

    calculate_payload = {
        "tariff_id": tariff.id,
        "route_length_m": 7,
        "quantity": 1,
        "extra_holes_count": 1,
        "extra_hole_price": 50,
        "addons": [{"slug": "chasing-work", "qty": 2}],
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

    create_payload = {
        **calculate_payload,
        "title": "Смета API",
        "comment": "Тестовый snapshot",
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

    list_resp = await async_client.get(
        "/api/manager/service-estimates?page=1&limit=20",
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_manager_service_estimates_requires_auth(async_client):
    resp = await async_client.post(
        "/api/manager/service-estimates/calculate",
        json={"category": "Wall", "route_length_m": 3, "quantity": 1},
    )
    assert resp.status_code == 401
