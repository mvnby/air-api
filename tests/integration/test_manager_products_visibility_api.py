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


@pytest.mark.asyncio
async def test_manager_product_detail_can_open_unpublished_product(async_client, db):
    headers = await _auth_headers(async_client)
    product = Product(
        title="Workspace Draft Product",
        slug="workspace-draft-product",
        price=1250,
        area=32,
        is_published=False,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    response = await async_client.get(
        f"/api/manager/products/{product.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == product.id
    assert payload["title"] == "Workspace Draft Product"
    assert payload["is_published"] is False


@pytest.mark.asyncio
async def test_manager_product_detail_returns_not_found(async_client):
    headers = await _auth_headers(async_client)

    response = await async_client.get(
        "/api/manager/products/99999999",
        headers=headers,
    )

    assert response.status_code == 404
