from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from api_contracts.tenant_offers import POSTGRESQL_INTEGER_MAX
from core.security import create_access_token
from crud.tenant_offer import TenantOfferDAO
from models import (
    Product,
    StaffUser,
    Storefront,
    Tenant,
    TenantAuditEvent,
    TenantMembership,
    TenantOffer,
)
from models.tenancy import TenantScope
from services.tenant_offer_service import TenantOfferService


async def _create_owner(
    session: AsyncSession,
    *,
    tenant_id: int,
    username: str,
) -> StaffUser:
    user = StaffUser(
        display_name=username,
        status="active",
        roles=["owner"],
        primary_role="owner",
        username=username,
    )
    session.add(user)
    await session.flush()
    session.add(
        TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=int(user.id),
            role="owner",
            status="active",
        )
    )
    await session.flush()
    return user


async def _create_second_tenant(
    session: AsyncSession,
) -> tuple[Tenant, Storefront]:
    tenant = Tenant(
        id=2,
        slug="tenant-b",
        display_name="Tenant B",
        status="active",
        is_system=False,
    )
    session.add(tenant)
    await session.flush()
    storefront = Storefront(
        id=2,
        tenant_id=int(tenant.id),
        slug="main",
        display_name="Tenant B Main",
        status="active",
        is_default=True,
    )
    session.add(storefront)
    await session.flush()
    return tenant, storefront


def _headers(user: StaffUser, *, request_id: str | None = None) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_source": "tenant-offer-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


@pytest.mark.asyncio
async def test_manager_tenant_offers_are_exactly_storefront_scoped_and_audited(
    async_client: AsyncClient,
    db: AsyncSession,
):
    tenant_b, storefront_b = await _create_second_tenant(db)
    owner_a = await _create_owner(db, tenant_id=1, username="offer-owner-a")
    owner_b = await _create_owner(
        db,
        tenant_id=int(tenant_b.id),
        username="offer-owner-b",
    )
    product = Product(title="Shared Model", slug="shared-model", price=1900)
    city_storefront = Storefront(
        id=3,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Orsha",
        status="active",
        is_default=False,
    )
    db.add_all([product, city_storefront])
    await db.commit()

    create_a = await async_client.post(
        "/api/manager/tenant-offers",
        headers=_headers(owner_a, request_id="offer-create-a-123"),
        json={
            "product_id": product.id,
            "price": 2100,
            "old_price": 2300,
            "is_published": True,
        },
    )
    assert create_a.status_code == 200, create_a.text
    offer_a = create_a.json()
    assert offer_a["storefront_id"] == 1
    assert offer_a["product_id"] == product.id
    assert "product_base_price" not in offer_a
    assert offer_a["price"] == 2100

    repeat_a = await async_client.post(
        "/api/manager/tenant-offers",
        headers=_headers(owner_a, request_id="offer-update-a-123"),
        json={
            "product_id": product.id,
            "price": 2050,
            "old_price": 2300,
            "is_published": True,
        },
    )
    assert repeat_a.status_code == 200, repeat_a.text
    assert repeat_a.json()["id"] == offer_a["id"]
    assert repeat_a.json()["price"] == 2050

    city_offer = await TenantOfferService.upsert_offer(
        db,
        payload={
            "product_id": product.id,
            "price": 2400,
            "old_price": None,
            "is_published": True,
            "status": "active",
        },
        tenant_scope=TenantScope(
            tenant_id=1,
            storefront_id=int(city_storefront.id),
            is_system=True,
        ),
        actor_username=str(owner_a.username),
        actor_staff_user_id=int(owner_a.id),
    )
    assert city_offer["price"] == 2400
    assert city_offer["storefront_id"] == city_storefront.id
    assert (
        await async_client.get(
            f"/api/manager/tenant-offers/{city_offer['id']}",
            headers=_headers(owner_a),
        )
    ).status_code == 404

    foreign_get = await async_client.get(
        f"/api/manager/tenant-offers/{offer_a['id']}",
        headers=_headers(owner_b),
    )
    foreign_patch = await async_client.patch(
        f"/api/manager/tenant-offers/{offer_a['id']}",
        headers=_headers(owner_b),
        json={"price": 1},
    )
    assert foreign_get.status_code == 404
    assert foreign_patch.status_code == 404

    list_b_before = await async_client.get(
        "/api/manager/tenant-offers",
        headers=_headers(owner_b),
    )
    assert list_b_before.status_code == 200
    assert list_b_before.json() == {"items": [], "total": 0}

    create_b = await async_client.post(
        "/api/manager/tenant-offers",
        headers=_headers(owner_b, request_id="offer-create-b-123"),
        json={
            "product_id": product.id,
            "price": 2600,
            "status": "disabled",
            "is_published": True,
        },
    )
    assert create_b.status_code == 200, create_b.text
    assert create_b.json()["storefront_id"] == storefront_b.id
    assert create_b.json()["price"] == 2600
    assert create_b.json()["status"] == "disabled"
    assert create_b.json()["is_published"] is False

    list_a = await async_client.get(
        "/api/manager/tenant-offers",
        headers=_headers(owner_a),
    )
    list_b = await async_client.get(
        "/api/manager/tenant-offers",
        headers=_headers(owner_b),
    )
    assert [item["id"] for item in list_a.json()["items"]] == [offer_a["id"]]
    assert [item["id"] for item in list_b.json()["items"]] == [create_b.json()["id"]]

    audit_a = await async_client.get(
        "/api/manager/tenant-offers/audit",
        headers=_headers(owner_a),
    )
    audit_b = await async_client.get(
        "/api/manager/tenant-offers/audit",
        headers=_headers(owner_b),
    )
    assert audit_a.status_code == 200
    assert audit_b.status_code == 200
    assert audit_a.json()["total"] == 2
    assert audit_a.json()["items"][0]["action"] == "tenant_offer.updated"
    assert audit_a.json()["items"][0]["actor_staff_user_id"] == owner_a.id
    assert audit_a.json()["items"][0]["change_set"]["price"] == {
        "before": 2100,
        "after": 2050,
    }
    assert {
        item["request_id"] for item in audit_a.json()["items"]
    } == {"offer-create-a-123", "offer-update-a-123"}
    assert {item["entity_id"] for item in audit_a.json()["items"]} == {
        offer_a["id"]
    }
    assert audit_b.json()["total"] == 1
    assert audit_b.json()["items"][0]["request_id"] == "offer-create-b-123"


@pytest.mark.asyncio
async def test_tenant_offer_rejects_invalid_price_and_unknown_product_without_audit(
    async_client: AsyncClient,
    db: AsyncSession,
):
    owner = await _create_owner(db, tenant_id=1, username="offer-validator")
    await db.commit()
    headers = _headers(owner)

    invalid_price = await async_client.post(
        "/api/manager/tenant-offers",
        headers=headers,
        json={"product_id": 1, "price": 500, "old_price": 400},
    )
    missing_product = await async_client.post(
        "/api/manager/tenant-offers",
        headers=headers,
        json={"product_id": 999999, "price": 500},
    )
    audit = await async_client.get(
        "/api/manager/tenant-offers/audit",
        headers=headers,
    )

    assert invalid_price.status_code == 422
    assert missing_product.status_code == 404
    assert audit.status_code == 200
    assert audit.json() == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_tenant_offer_patch_rejects_explicit_null_except_old_price(
    async_client: AsyncClient,
    db: AsyncSession,
):
    owner = await _create_owner(db, tenant_id=1, username="offer-null-validator")
    product = Product(title="Nullable Model", slug="nullable-model", price=1000)
    db.add(product)
    await db.commit()
    headers = _headers(owner)
    created = await async_client.post(
        "/api/manager/tenant-offers",
        headers=headers,
        json={
            "product_id": product.id,
            "price": 1200,
            "old_price": 1400,
            "is_published": True,
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    offer_id = created.json()["id"]

    for field in ("price", "is_published", "status"):
        response = await async_client.patch(
            f"/api/manager/tenant-offers/{offer_id}",
            headers=headers,
            json={field: None},
        )
        assert response.status_code == 422, (field, response.text)

    clear_old_price = await async_client.patch(
        f"/api/manager/tenant-offers/{offer_id}",
        headers=headers,
        json={"old_price": None},
    )
    assert clear_old_price.status_code == 200, clear_old_price.text
    assert clear_old_price.json()["old_price"] is None
    assert clear_old_price.json()["price"] == 1200
    assert clear_old_price.json()["status"] == "active"
    assert clear_old_price.json()["is_published"] is True


@pytest.mark.asyncio
async def test_tenant_offer_rejects_values_outside_postgresql_integer_range(
    async_client: AsyncClient,
    db: AsyncSession,
):
    owner = await _create_owner(db, tenant_id=1, username="offer-int-validator")
    product = Product(title="Integer Model", slug="integer-model", price=1000)
    db.add(product)
    await db.commit()
    headers = _headers(owner)
    overflow = POSTGRESQL_INTEGER_MAX + 1

    for payload in (
        {"product_id": overflow, "price": 1000},
        {"product_id": product.id, "price": overflow},
        {"product_id": product.id, "price": 1000, "old_price": overflow},
    ):
        response = await async_client.post(
            "/api/manager/tenant-offers",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422, (payload, response.text)

    for offer_id in (0, overflow):
        get_response = await async_client.get(
            f"/api/manager/tenant-offers/{offer_id}",
            headers=headers,
        )
        patch_response = await async_client.patch(
            f"/api/manager/tenant-offers/{offer_id}",
            headers=headers,
            json={"price": 1000},
        )
        assert get_response.status_code == 422, get_response.text
        assert patch_response.status_code == 422, patch_response.text


@pytest.mark.asyncio
async def test_database_rejects_cross_tenant_storefront_offer(db_engine):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        tenant_b, storefront_b = await _create_second_tenant(session)
        product = Product(title="Constraint Model", slug="constraint-model", price=1000)
        session.add(product)
        await session.commit()

        session.add(
            TenantOffer(
                tenant_id=1,
                storefront_id=int(storefront_b.id),
                product_id=int(product.id),
                price=1000,
                created_by_username="constraint-test",
                updated_by_username="constraint-test",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_offer_and_audit_roll_back_together_when_audit_write_fails(
    db_engine,
    monkeypatch,
):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        product = Product(title="Rollback Model", slug="rollback-model", price=1000)
        session.add(product)
        await session.flush()
        offer = TenantOffer(
            tenant_id=1,
            storefront_id=1,
            product_id=int(product.id),
            price=1200,
            created_by_username="seed",
            updated_by_username="seed",
        )
        session.add(offer)
        await session.commit()
        offer_id = int(offer.id)

    def fail_audit_write(_session, _event: TenantAuditEvent) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(TenantOfferDAO, "add_audit_event", fail_audit_write)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    async with factory() as session:
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            await TenantOfferService.update_offer(
                session,
                offer_id=offer_id,
                payload={"price": 1300},
                tenant_scope=scope,
                actor_username="rollback-test",
                actor_staff_user_id=None,
            )

    async with factory() as session:
        stored_offer = await session.get(TenantOffer, offer_id)
        audit_rows = (
            await session.execute(select(TenantAuditEvent))
        ).scalars().all()
        assert stored_offer is not None
        assert stored_offer.price == 1200
        assert stored_offer.updated_by_username == "seed"
        assert audit_rows == []
