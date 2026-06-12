import pytest

from core.config import settings
from models import Product, ProductSeries
from services.catalog_revision_service import CatalogRevisionService


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_brands_crud(async_client):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={
            "title": "Brand Test TCL",
            "logo_url": "https://example.com/tcl.png",
            "description": "Test description",
            "sort_order": 50,
            "is_published": True,
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["title"] == "Brand Test TCL"
    assert created["slug"] == "brand-test-tcl"
    brand_id = created["id"]

    list_resp = await async_client.get("/api/manager/brands", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["id"] == brand_id for item in items)

    update_resp = await async_client.put(
        f"/api/manager/brands/{brand_id}",
        headers=headers,
        json={
            "title": "Brand Test TCL Updated",
            "is_published": False,
            "sort_order": 5,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["title"] == "Brand Test TCL Updated"
    assert updated["is_published"] is False
    assert updated["sort_order"] == 5

    delete_resp = await async_client.delete(f"/api/manager/brands/{brand_id}", headers=headers)
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_manager_brand_delete_forbidden_when_products_linked(async_client, db):
    headers = await _auth_headers(async_client)

    create_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={"title": "Brand Linked", "slug": "brand-linked"},
    )
    assert create_resp.status_code == 200
    brand_id = create_resp.json()["id"]

    product = Product(
        title="Brand Linked Product",
        slug="brand-linked-product",
        price=1000,
        area=20,
        brand_id=brand_id,
    )
    db.add(product)
    await db.commit()

    delete_resp = await async_client.delete(f"/api/manager/brands/{brand_id}", headers=headers)
    assert delete_resp.status_code == 400
    assert "привязаны товары" in delete_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_manager_brand_series_crud(async_client):
    headers = await _auth_headers(async_client)

    brand_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={"title": "Series Brand", "slug": "series-brand"},
    )
    assert brand_resp.status_code == 200
    brand_id = brand_resp.json()["id"]

    create_resp = await async_client.post(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
        json={
            "title": "FreshIN",
            "description": "Fresh air product line",
            "hero_image": "/media/series/freshin.webp",
            "features": [" fresh air ", "", "Wi-Fi", "Wi-Fi"],
            "sort_order": 10,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    assert created["title"] == "FreshIN"
    assert created["slug"] == "freshin"
    assert created["features"] == ["fresh air", "Wi-Fi"]
    assert created["products_count"] == 0
    series_id = created["id"]

    list_resp = await async_client.get(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()["items"]] == [series_id]

    update_resp = await async_client.put(
        f"/api/manager/brands/{brand_id}/series/{series_id}",
        headers=headers,
        json={
            "title": "FreshIN Updated",
            "slug": "freshin-updated",
            "features": ["Fresh air", "Self-cleaning"],
            "is_published": False,
            "sort_order": 3,
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["title"] == "FreshIN Updated"
    assert updated["slug"] == "freshin-updated"
    assert updated["features"] == ["Fresh air", "Self-cleaning"]
    assert updated["is_published"] is False
    assert updated["sort_order"] == 3

    delete_resp = await async_client.delete(
        f"/api/manager/brands/{brand_id}/series/{series_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_manager_brand_series_slug_unique_per_brand(async_client):
    headers = await _auth_headers(async_client)

    brand_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={"title": "Unique Series Brand", "slug": "unique-series-brand"},
    )
    assert brand_resp.status_code == 200
    brand_id = brand_resp.json()["id"]

    first_resp = await async_client.post(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
        json={"title": "Elite", "slug": "elite"},
    )
    assert first_resp.status_code == 200

    duplicate_resp = await async_client.post(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
        json={"title": "Elite Copy", "slug": "elite"},
    )
    assert duplicate_resp.status_code == 400
    assert "у этого бренда" in duplicate_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_manager_brand_series_delete_forbidden_when_products_linked(async_client, db):
    headers = await _auth_headers(async_client)

    brand_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={"title": "Linked Series Brand", "slug": "linked-series-brand"},
    )
    assert brand_resp.status_code == 200
    brand_id = brand_resp.json()["id"]

    series = ProductSeries(
        title="Linked Series",
        slug="linked-series",
        brand_id=brand_id,
        is_published=True,
    )
    db.add(series)
    await db.flush()

    product = Product(
        title="Linked Series Product",
        slug="linked-series-product",
        price=1000,
        area=20,
        brand_id=brand_id,
        series_id=series.id,
    )
    db.add(product)
    await db.commit()

    delete_resp = await async_client.delete(
        f"/api/manager/brands/{brand_id}/series/{series.id}",
        headers=headers,
    )
    assert delete_resp.status_code == 400
    assert "привязаны товары" in delete_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_manager_brand_series_list_auto_creates_series_from_product_specs(async_client, db):
    headers = await _auth_headers(async_client)

    brand_resp = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={"title": "KingHome Auto Series", "slug": "kinghome-auto-series"},
    )
    assert brand_resp.status_code == 200
    brand_id = brand_resp.json()["id"]

    products = [
        Product(
            title="KINGHOME Cosmo KWH09AWAXB-K6DNA3B",
            slug="kinghome-auto-cosmo-1",
            price=1000,
            area=25,
            brand_id=brand_id,
            specs={"brand": "KINGHOME", "series": "COSMO inverter R32 WI-FI"},
        ),
        Product(
            title="KINGHOME Cosmo KWH12AWBXB-K6DNA3D",
            slug="kinghome-auto-cosmo-2",
            price=1200,
            area=35,
            brand_id=brand_id,
            specs={"brand": "KINGHOME", "series": "COSMO inverter R32 WI-FI"},
        ),
        Product(
            title="KINGHOME Luna Matt KWH09AYAXB-K6DNA5B",
            slug="kinghome-auto-luna-1",
            price=1300,
            area=25,
            brand_id=brand_id,
            specs={"brand": "KINGHOME", "series": "LUNA Matt inverter R32 WI-FI"},
        ),
    ]
    db.add_all(products)
    await db.commit()

    list_resp = await async_client.get(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
    )

    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    by_slug = {item["slug"]: item for item in items}
    assert by_slug["cosmo"]["title"] == "COSMO"
    assert by_slug["cosmo"]["products_count"] == 2
    assert by_slug["luna-matt"]["title"] == "LUNA Matt"
    assert by_slug["luna-matt"]["products_count"] == 1
    after_first_revision = await CatalogRevisionService.get_current(db)

    db.expire_all()
    for product in products:
        updated = await db.get(Product, product.id)
        assert updated.series_id is not None

    second_list_resp = await async_client.get(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
    )
    assert second_list_resp.status_code == 200, second_list_resp.text
    assert second_list_resp.json()["items"] == items
    after_second_revision = await CatalogRevisionService.get_current(db)
    assert after_second_revision["revision"] == after_first_revision["revision"]
