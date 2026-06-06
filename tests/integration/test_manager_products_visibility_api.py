import pytest

from core.config import settings
from models import Product


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_products_list_can_show_unpublished_product(async_client, db):
    headers = await _auth_headers(async_client)
    marker = "MANAGERHIDDEN466"
    product = Product(
        title=f"{marker} Draft Product",
        slug=f"{marker.lower()}-draft-product",
        price=1000,
        area=25,
        is_published=False,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    response = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={"search": marker, "limit": 100},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    match = next(item for item in items if item["id"] == product.id)
    assert match["is_published"] is False
