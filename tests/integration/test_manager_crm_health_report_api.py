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
async def test_manager_crm_health_report_returns_metrics(async_client):
    headers = await _auth_headers(async_client)

    bad_req = await async_client.post(
        "/api/manager/leads",
        headers=headers,
        json={
            "source": "manager",
            "name": "Bad Email",
            "email": "wrong-email",
            "request_text": "telemetry",
        },
    )
    assert bad_req.status_code == 422

    report_resp = await async_client.get("/api/manager/crm/health-report?hours=24", headers=headers)
    assert report_resp.status_code == 200
    data = report_resp.json()

    assert data["window_hours"] == 24
    assert data["events_total"] >= 1
    assert data["errors_total"] >= 1
    assert data["invalid_payload_errors"] >= 1
    assert "qualify_success_total" in data
    assert "qualify_success_without_manual_overwrite_pct" in data

