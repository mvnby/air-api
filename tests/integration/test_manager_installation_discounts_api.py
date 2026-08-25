import pytest
from sqlmodel import select

from core.config import settings
from models import GlobalConfig, InstallationDiscountPolicy, Product
from services.product_supply_metrics_service import ProductSupplyMetricsService


async def _auth_headers(async_client):
    login_response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_can_configure_policy_and_visible_product_exceptions(
    async_client,
    db,
):
    product = Product(
        title="Low-margin conditioner",
        slug="low-margin-conditioner",
        price=1_500,
        is_published=True,
    )
    db.add(product)
    db.add(GlobalConfig(key="install_discount", value="100"))
    await db.commit()
    await db.refresh(product)
    headers = await _auth_headers(async_client)

    initial = await async_client.get(
        "/api/manager/installation-discounts",
        headers=headers,
    )
    assert initial.status_code == 200
    assert initial.json()["policy"] == {
        "is_enabled": False,
        "default_discount": 100,
        "minimum_margin": 350,
    }
    assert initial.json()["items"] == []

    updated_policy = await async_client.put(
        "/api/manager/installation-discounts/policy",
        headers=headers,
        json={
            "is_enabled": True,
            "default_discount": 150,
            "minimum_margin": 400,
        },
    )
    assert updated_policy.status_code == 200
    assert updated_policy.json() == {
        "is_enabled": True,
        "default_discount": 150,
        "minimum_margin": 400,
    }
    assert (
        await db.execute(
            select(GlobalConfig.value).where(GlobalConfig.key == "install_discount")
        )
    ).scalar_one() == "0"

    search = await async_client.get(
        "/api/manager/installation-discounts/products/search",
        headers=headers,
        params={"q": "Low-margin"},
    )
    assert search.status_code == 200
    search_item = search.json()["items"][0]
    assert search_item["product_id"] == product.id
    assert search_item["purchase_cost"] is None
    assert search_item["status"] == "blocked_missing_cost"

    disabled = await async_client.put(
        f"/api/manager/installation-discounts/products/{product.id}",
        headers=headers,
        json={"discount_amount": 0},
    )
    assert disabled.status_code == 200
    assert disabled.json()["configured_discount"] == 0
    assert disabled.json()["applied_discount"] == 0
    assert disabled.json()["has_override"] is True
    assert disabled.json()["status"] == "disabled"

    listed = await async_client.get(
        "/api/manager/installation-discounts",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Low-margin conditioner"

    removed = await async_client.delete(
        f"/api/manager/installation-discounts/products/{product.id}",
        headers=headers,
    )
    assert removed.status_code == 204
    inherited = await async_client.get(
        "/api/manager/installation-discounts",
        headers=headers,
    )
    assert inherited.json()["total"] == 0

    rolled_back = await async_client.put(
        "/api/manager/installation-discounts/policy",
        headers=headers,
        json={
            "is_enabled": False,
            "default_discount": 150,
            "minimum_margin": 400,
        },
    )
    assert rolled_back.status_code == 200
    assert (
        await db.execute(
            select(GlobalConfig.value).where(GlobalConfig.key == "install_discount")
        )
    ).scalar_one() == "150"


@pytest.mark.asyncio
async def test_manager_installation_discounts_require_auth(async_client):
    response = await async_client.get("/api/manager/installation-discounts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_public_product_exposes_only_resolved_discount_not_margin_policy(
    async_client,
    db,
    monkeypatch,
):
    product = Product(
        title="Public conditioner",
        slug="public-discount-conditioner",
        price=2_000,
        is_published=True,
    )
    db.add(product)
    db.add(
        InstallationDiscountPolicy(
            id=1,
            is_enabled=True,
            default_discount=100,
            minimum_margin=350,
        )
    )
    await db.commit()

    async def low_margin_metrics(_session, products):
        return {int(item.id): {"min_cost_byn": 1_700} for item in products}

    monkeypatch.setattr(
        ProductSupplyMetricsService,
        "compute_for_products",
        low_margin_metrics,
    )

    response = await async_client.get(f"/api/v1/products/{product.slug}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["installation_discount"] == 0
    serialized = str(payload)
    assert "minimum_margin" not in serialized
    assert "purchase_cost" not in serialized
    assert "configured_discount" not in serialized
    assert "discount_policy" not in serialized
