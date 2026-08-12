import pytest
from sqlmodel import select

from core.config import settings
from models import Brand, Product, ProductSeries


async def _auth_headers(async_client) -> dict[str, str]:
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
async def test_manager_product_series_assignment_contract(async_client, db):
    headers = await _auth_headers(async_client)
    first_brand = Brand(title="Assignment One", slug="assignment-one")
    second_brand = Brand(title="Assignment Two", slug="assignment-two")
    db.add_all([first_brand, second_brand])
    await db.flush()
    first_series = ProductSeries(
        title="Canonical One",
        slug="canonical-one",
        brand_id=first_brand.id,
    )
    replacement_series = ProductSeries(
        title="Canonical Replacement",
        slug="canonical-replacement",
        brand_id=first_brand.id,
    )
    wrong_brand_series = ProductSeries(
        title="Wrong Brand",
        slug="wrong-brand",
        brand_id=second_brand.id,
    )
    db.add_all([first_series, replacement_series, wrong_brand_series])
    await db.flush()
    first_brand_id = int(first_brand.id)
    second_brand_id = int(second_brand.id)
    first_series_id = int(first_series.id)
    replacement_series_id = int(replacement_series.id)
    wrong_brand_series_id = int(wrong_brand_series.id)
    await db.commit()

    create = await async_client.post(
        "/api/manager/products",
        headers=headers,
        json={
            "title": "Manual series product",
            "price": 1000,
            "brand_id": first_brand_id,
            "series_id": first_series_id,
            "specs": {"Серия модели": "Stale alias", "series": "Stale canonical"},
        },
    )
    assert create.status_code == 200, create.text
    product_id = int(
        (
            await db.execute(
                select(Product.id).where(Product.title == "Manual series product")
            )
        ).scalar_one()
    )
    db.expire_all()
    product = await db.get(Product, product_id)
    assert product.series_id == first_series_id
    assert product.series_assignment_source == "manual"
    assert product.specs["series"] == "Canonical One"
    assert product.specs["__typed_specs"]["series"]["value"] == "Canonical One"
    assert "Серия модели" not in product.specs

    omitted_update = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={"specs": {"series": "Importer-looking stale value", "area_m2": 25}},
    )
    assert omitted_update.status_code == 200, omitted_update.text
    db.expire_all()
    product = await db.get(Product, product_id)
    assert product.series_id == first_series_id
    assert product.specs["area_m2"] == 25
    assert product.specs["series"] == "Canonical One"

    wrong_brand = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={"brand_id": second_brand_id},
    )
    assert wrong_brand.status_code == 400
    assert set(wrong_brand.json()["detail"]["field_errors"]) == {"brand_id", "series_id"}

    wrong_series = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={"series_id": wrong_brand_series_id},
    )
    assert wrong_series.status_code == 400
    assert "series_id" in wrong_series.json()["detail"]["field_errors"]

    replace = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={
            "series_id": replacement_series_id,
            "specs": {"Линейка": "Stale alias", "area_m2": 35},
        },
    )
    assert replace.status_code == 200, replace.text
    db.expire_all()
    product = await db.get(Product, product_id)
    assert product.series_id == replacement_series_id
    assert product.specs["area_m2"] == 35
    assert product.specs["series"] == "Canonical Replacement"
    assert product.specs["__typed_specs"]["series"]["value"] == "Canonical Replacement"
    assert "Линейка" not in product.specs

    duplicate = await async_client.post(
        f"/api/manager/products/{product_id}/duplicate",
        headers=headers,
        json={"title": "Manual series product copy"},
    )
    assert duplicate.status_code == 200, duplicate.text
    duplicated = (
        await db.execute(
            select(Product).where(Product.title == "Manual series product copy")
        )
    ).scalar_one()
    assert duplicated.series_id == replacement_series_id
    assert duplicated.series_assignment_source == "manual"
    assert duplicated.specs["series"] == "Canonical Replacement"

    clear = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={"series_id": None, "specs": {"Серия": "Must not rederive", "area_m2": 45}},
    )
    assert clear.status_code == 200, clear.text
    db.expire_all()
    product = await db.get(Product, product_id)
    assert product.series_id is None
    assert product.series_assignment_source == "manual"
    assert product.specs["area_m2"] == 45
    assert "series" not in product.specs
    assert "series" not in product.specs.get("__typed_specs", {})
    assert "Серия" not in product.specs


@pytest.mark.asyncio
async def test_manager_product_create_omitted_series_keeps_legacy_derivation(async_client, db):
    headers = await _auth_headers(async_client)
    brand = Brand(title="Legacy Derive", slug="legacy-derive")
    db.add(brand)
    await db.commit()

    response = await async_client.post(
        "/api/manager/products",
        headers=headers,
        json={
            "title": "Legacy Derive Model",
            "price": 900,
            "brand_id": brand.id,
            "specs": {"Серия кондиционера": "Legacy Line inverter R32"},
        },
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    product = (
        await db.execute(
            select(Product).where(Product.title == "Legacy Derive Model")
        )
    ).scalar_one()
    series = await db.get(ProductSeries, product.series_id)
    assert series.title == "Legacy Line"
    assert product.series_assignment_source == "derived"
    assert product.specs["series"] == "Legacy Line"
