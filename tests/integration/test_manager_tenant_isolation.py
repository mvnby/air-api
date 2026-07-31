from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.security import create_access_token
from models import (
    Customer,
    CustomerRequisitesRecognition,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
)
from models.common import CustomerType


async def _create_tenant(
    db,
    *,
    slug: str,
    is_system: bool = False,
) -> tuple[Tenant, Storefront]:
    tenant = Tenant(
        id=2,
        slug=slug,
        display_name=slug.upper(),
        kind="independent_seller",
        status="active",
        is_system=is_system,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        id=2,
        tenant_id=int(tenant.id),
        slug="main",
        display_name=f"{slug.upper()} Main",
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    return tenant, storefront


async def _create_staff(
    db,
    *,
    tenant_id: int | None,
    username: str,
    membership_role: str = "owner",
    membership_status: str = "active",
    global_role: str = "owner",
) -> StaffUser:
    user = StaffUser(
        display_name=username,
        status="active",
        primary_role=global_role,
        roles=[global_role],
        username=username,
    )
    db.add(user)
    await db.flush()
    if tenant_id is not None:
        db.add(
            TenantMembership(
                tenant_id=tenant_id,
                staff_user_id=int(user.id),
                role=membership_role,
                status=membership_status,
            )
        )
        await db.flush()
    return user


def _headers(user: StaffUser, *, claimed_role: str = "owner") -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "role": claimed_role,
            "auth_source": "tenant-isolation-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_customer_api_isolates_tenants_and_legacy_rows(
    async_client: AsyncClient,
    db,
):
    tenant_b, storefront_b = await _create_tenant(db, slug="tenant-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="owner-b",
    )
    legacy = Customer(
        name="Legacy MVN",
        phone="+375290000001",
        type=CustomerType.individual,
    )
    customer_a = Customer(
        tenant_id=1,
        name="Tenant A",
        phone="+375290000002",
        type=CustomerType.individual,
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="Tenant B",
        phone="+375290000003",
        type=CustomerType.individual,
    )
    recognition_b = CustomerRequisitesRecognition(
        tenant_id=int(tenant_b.id),
        source="manager",
        status="recognized",
        raw_text="ООО Tenant B УНП 123456789",
        extracted_json={
            "name": "ООО Tenant B",
            "inn": "123456789",
        },
        validation_flags={
            "field_errors": {},
            "warnings": {},
            "is_valid": True,
        },
    )
    db.add_all([legacy, customer_a, customer_b, recognition_b])
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    me_b = await async_client.get("/api/manager/me", headers=headers_b)
    assert me_b.status_code == 200
    assert me_b.json()["tenant_id"] == tenant_b.id
    assert me_b.json()["storefront_id"] == storefront_b.id

    list_a = await async_client.get(
        "/api/manager/customers?only_with_orders=false",
        headers=headers_a,
    )
    list_b = await async_client.get(
        "/api/manager/customers?only_with_orders=false",
        headers=headers_b,
    )
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert {item["id"] for item in list_a.json()["items"]} == {
        legacy.id,
        customer_a.id,
    }
    assert {item["id"] for item in list_b.json()["items"]} == {
        customer_b.id,
    }

    assert (
        await async_client.get(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
        )
    ).status_code == 404
    assert (
        await async_client.patch(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
            json={"name": "Cross-tenant write"},
        )
    ).status_code == 404
    assert (
        await async_client.delete(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
        )
    ).status_code == 404

    for suffix in ("docs", "branches", "contracts", "reconciliation"):
        response = await async_client.get(
            f"/api/manager/customers/{customer_b.id}/{suffix}",
            headers=headers_a,
        )
        assert response.status_code == 404, suffix

    recognition_response = await async_client.post(
        f"/api/manager/customers/requisites/{recognition_b.id}/confirm",
        headers=headers_a,
        json={"action": "create"},
    )
    assert recognition_response.status_code == 404

    claim_legacy = await async_client.patch(
        f"/api/manager/customers/{legacy.id}",
        headers=headers_a,
        json={"name": "Legacy MVN claimed"},
    )
    assert claim_legacy.status_code == 200
    await db.refresh(legacy)
    assert legacy.tenant_id == 1


@pytest.mark.asyncio
async def test_owner_staff_management_is_tenant_scoped(
    async_client: AsyncClient,
    db,
):
    tenant_b, _ = await _create_tenant(db, slug="staff-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="staff-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="staff-owner-b",
    )
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    list_a = await async_client.get("/api/manager/staff", headers=headers_a)
    list_b = await async_client.get("/api/manager/staff", headers=headers_b)
    assert {item["id"] for item in list_a.json()["items"]} == {owner_a.id}
    assert {item["id"] for item in list_b.json()["items"]} == {owner_b.id}

    cross_patch = await async_client.patch(
        f"/api/manager/staff/{owner_b.id}",
        headers=headers_a,
        json={"display_name": "Must not change"},
    )
    assert cross_patch.status_code == 404

    created = await async_client.post(
        "/api/manager/staff",
        headers=headers_a,
        json={
            "display_name": "Tenant A Manager",
            "status": "active",
            "primary_role": "manager",
            "username": "tenant-a-manager",
        },
    )
    assert created.status_code == 200
    created_id = created.json()["id"]
    membership = (
        await db.execute(
            select(TenantMembership).where(
                TenantMembership.staff_user_id == created_id
            )
        )
    ).scalar_one()
    assert membership.tenant_id == 1
    assert membership.role == "manager"
    assert membership.status == "active"

    shared = await _create_staff(
        db,
        tenant_id=1,
        username="shared-staff",
    )
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(shared.id),
            role="owner",
            status="active",
        )
    )
    await db.commit()

    shared_identity_patch = await async_client.patch(
        f"/api/manager/staff/{shared.id}",
        headers=headers_b,
        json={"display_name": "Tenant B must not rewrite shared identity"},
    )
    assert shared_identity_patch.status_code == 400

    membership_patch = await async_client.patch(
        f"/api/manager/staff/{shared.id}",
        headers=headers_b,
        json={"status": "blocked", "primary_role": "manager"},
    )
    assert membership_patch.status_code == 200
    memberships = (
        await db.execute(
            select(TenantMembership)
            .where(TenantMembership.staff_user_id == shared.id)
            .order_by(TenantMembership.tenant_id.asc())
        )
    ).scalars().all()
    assert [
        (item.tenant_id, item.role, item.status)
        for item in memberships
    ] == [
        (1, "owner", "active"),
        (tenant_b.id, "manager", "suspended"),
    ]
    await db.refresh(shared)
    assert shared.status == "active"
    assert shared.display_name == "shared-staff"


@pytest.mark.asyncio
async def test_manager_auth_uses_membership_and_fails_closed(
    async_client: AsyncClient,
    db,
):
    tenant_b, _ = await _create_tenant(db, slug="auth-b")
    membership_manager = await _create_staff(
        db,
        tenant_id=1,
        username="membership-manager",
        membership_role="manager",
        global_role="owner",
    )
    suspended = await _create_staff(
        db,
        tenant_id=1,
        username="suspended-owner",
        membership_status="suspended",
    )
    missing = await _create_staff(
        db,
        tenant_id=None,
        username="missing-membership",
    )
    ambiguous = await _create_staff(
        db,
        tenant_id=1,
        username="ambiguous-owner",
    )
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(ambiguous.id),
            role="owner",
            status="active",
        )
    )
    await db.commit()

    manager_me = await async_client.get(
        "/api/manager/me",
        headers=_headers(membership_manager, claimed_role="owner"),
    )
    assert manager_me.status_code == 200
    assert manager_me.json()["role"] == "manager"
    assert (
        await async_client.get(
            "/api/manager/staff",
            headers=_headers(membership_manager, claimed_role="owner"),
        )
    ).status_code == 403

    for user in (suspended, missing, ambiguous):
        response = await async_client.get(
            "/api/manager/me",
            headers=_headers(user),
        )
        assert response.status_code == 403
