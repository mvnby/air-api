from datetime import timedelta

import pytest
from httpx import AsyncClient

from core.config import settings
from core.security import create_access_token
from models import (
    Product,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
    TenantOffer,
)
from services.manager_storefront_selector_service import MANAGER_STOREFRONT_HEADER


async def _create_owner(db, *, tenant_id: int, username: str) -> StaffUser:
    owner = StaffUser(
        display_name=username,
        status="active",
        roles=["owner"],
        primary_role="owner",
        username=username,
    )
    db.add(owner)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    return owner


def _headers(
    owner: StaffUser,
    *,
    storefront_slug: str | None = None,
) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": owner.username,
            "staff_user_id": owner.id,
            "auth_source": "manager-storefront-selector-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    headers = {"Authorization": f"Bearer {token}"}
    if storefront_slug is not None:
        headers[MANAGER_STOREFRONT_HEADER] = storefront_slug
    return headers


@pytest.mark.asyncio
async def test_manager_can_select_only_an_active_storefront_in_own_tenant(
    async_client: AsyncClient,
    db,
):
    owner = await _create_owner(db, tenant_id=1, username="storefront-owner")
    orsha = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        city="Орша",
        is_default=False,
    )
    disabled = Storefront(
        id=3,
        tenant_id=1,
        slug="disabled-city",
        display_name="Disabled City",
        status="disabled",
        is_default=False,
    )
    foreign_tenant = Tenant(
        id=2,
        slug="foreign",
        display_name="Foreign",
        status="active",
        is_system=False,
    )
    foreign_storefront = Storefront(
        id=4,
        tenant_id=2,
        slug="foreign-only",
        display_name="Foreign only",
        status="active",
        is_default=True,
    )
    product = Product(
        title="Scoped storefront model",
        slug="scoped-storefront-model",
        price=1000,
    )
    db.add(foreign_tenant)
    await db.flush()
    db.add_all([orsha, disabled, foreign_storefront, product])
    await db.flush()
    main_offer = TenantOffer(
        tenant_id=1,
        storefront_id=1,
        product_id=int(product.id),
        price=1100,
        is_published=True,
        created_by_username="seed",
        updated_by_username="seed",
    )
    orsha_offer = TenantOffer(
        tenant_id=1,
        storefront_id=int(orsha.id),
        product_id=int(product.id),
        price=1200,
        is_published=True,
        created_by_username="seed",
        updated_by_username="seed",
    )
    db.add_all([main_offer, orsha_offer])
    await db.commit()

    default_me = await async_client.get("/api/manager/me", headers=_headers(owner))
    selected_me = await async_client.get(
        "/api/manager/me",
        headers=_headers(owner, storefront_slug="ORSHA"),
    )
    assert default_me.status_code == 200
    assert default_me.json()["storefront_id"] == 1
    assert selected_me.status_code == 200
    assert selected_me.json()["tenant_id"] == 1
    assert selected_me.json()["storefront_id"] == orsha.id

    default_offers = await async_client.get(
        "/api/manager/tenant-offers",
        headers=_headers(owner),
    )
    selected_offers = await async_client.get(
        "/api/manager/tenant-offers",
        headers=_headers(owner, storefront_slug="orsha"),
    )
    assert [item["id"] for item in default_offers.json()["items"]] == [
        main_offer.id
    ]
    assert [item["id"] for item in selected_offers.json()["items"]] == [
        orsha_offer.id
    ]

    available = await async_client.get(
        "/api/manager/storefronts",
        headers=_headers(owner, storefront_slug="orsha"),
    )
    assert available.status_code == 200
    assert [item["slug"] for item in available.json()["items"]] == ["main", "orsha"]
    assert {
        item["slug"] for item in available.json()["items"] if item["is_current"]
    } == {"orsha"}
    assert "id" not in available.json()["items"][0]

    for forbidden_slug in ("", "../../main", "disabled-city", "foreign-only"):
        response = await async_client.get(
            "/api/manager/me",
            headers=_headers(owner, storefront_slug=forbidden_slug),
        )
        assert response.status_code == 403, forbidden_slug
        assert response.json()["detail"] == "Storefront access denied"


@pytest.mark.asyncio
async def test_storefront_header_does_not_bypass_ambiguous_tenant_membership(
    async_client: AsyncClient,
    db,
):
    tenant_b = Tenant(
        id=2,
        slug="second-membership",
        display_name="Second membership",
        status="active",
        is_system=False,
    )
    storefront_b = Storefront(
        id=2,
        tenant_id=2,
        slug="main",
        display_name="Second main",
        status="active",
        is_default=True,
    )
    orsha = Storefront(
        id=3,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        is_default=False,
    )
    db.add(tenant_b)
    await db.flush()
    db.add_all([storefront_b, orsha])
    await db.flush()
    owner = await _create_owner(db, tenant_id=1, username="ambiguous-owner")
    db.add(
        TenantMembership(
            tenant_id=2,
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    await db.commit()

    response = await async_client.get(
        "/api/manager/me",
        headers=_headers(owner, storefront_slug="orsha"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Active tenant membership required"


@pytest.mark.asyncio
async def test_legacy_system_manager_can_select_only_a_system_tenant_storefront(
    async_client: AsyncClient,
    db,
):
    orsha = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        is_default=False,
    )
    db.add(orsha)
    await db.commit()
    token = create_access_token(
        {"sub": settings.ADMIN_USERNAME},
        expires_delta=timedelta(minutes=10),
    )

    response = await async_client.get(
        "/api/manager/me",
        headers={
            "Authorization": f"Bearer {token}",
            MANAGER_STOREFRONT_HEADER: "orsha",
        },
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == 1
    assert response.json()["storefront_id"] == orsha.id
