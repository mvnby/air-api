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
async def test_manager_crm_flow_lead_qualify_patch_order_smoke(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "CRM Flow Smoke",
            "email": "crm-flow-smoke@example.com",
            "request_text": "Smoke flow",
        },
    )
    assert create_resp.status_code == 200
    lead_id = create_resp.json()["id"]

    qualify_resp = await async_client.post(
        f"/api/manager/leads/{lead_id}/qualify",
        headers=headers,
        json={
            "name": "CRM Flow Smoke",
            "email": "crm-flow-smoke@example.com",
            "inn": "391398328",
            "full_legal_name": "ООО CRM FLOW",
            "legal_address": "г. Витебск, ул. Тестовая, 1",
            "iban": "BY12ALFA30120000000000000000",
            "bic": "ALFABY2X",
            "bank_name": "Альфа-Банк",
            "order_comment": "CRM smoke qualify",
        },
    )
    assert qualify_resp.status_code == 200
    qualified = qualify_resp.json()
    order_id = qualified["order_id"]
    customer_id = qualified["customer_id"]

    customer_resp = await async_client.get(f"/api/manager/customers/{customer_id}", headers=headers)
    assert customer_resp.status_code == 200
    customer = customer_resp.json()
    assert customer["inn"] == "391398328"
    assert customer["iban"] == "BY12ALFA30120000000000000000"
    assert customer["bic"] == "ALFABY2X"
    assert customer["bank_name"] == "Альфа-Банк"

    order_patch_resp = await async_client.patch(
        f"/api/manager/orders/{order_id}",
        headers=headers,
        json={"status": "negotiation", "comment": "CRM smoke patch"},
    )
    assert order_patch_resp.status_code == 200
    patched = order_patch_resp.json()
    assert patched["id"] == order_id
    assert patched["status"] == "negotiation"

    health_resp = await async_client.get("/api/manager/crm/health-report?hours=24", headers=headers)
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert health["qualify_success_total"] >= 1
