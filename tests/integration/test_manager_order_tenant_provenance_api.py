from datetime import datetime, timezone

import pytest
from sqlmodel import select

from core.config import settings
from models import Order


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_order_import_assigns_server_resolved_scope(async_client, db):
    response = await async_client.post(
        "/api/manager/orders/import",
        headers=await _auth_headers(async_client),
        json={
            "package": {
                "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "manager",
                "orders": [
                    {
                        "source_id": 7001,
                        "status": "negotiation",
                        "title": "Scoped transfer import",
                    }
                ],
            }
        },
    )

    assert response.status_code == 200, response.text
    order_id = response.json()["created_order_ids"][0]
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one()
    assert (order.tenant_id, order.storefront_id) == (1, 1)
