from datetime import timedelta

import pytest
from httpx import AsyncClient

from core.security import create_access_token
from models import Brand, ProductSeries, StaffUser, Supplier, TenantMembership


async def _owner_headers(db) -> dict[str, str]:
    owner = StaffUser(
        display_name="Warranty policy owner",
        status="active",
        roles=["owner"],
        primary_role="owner",
        username="warranty-policy-owner",
    )
    db.add(owner)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=int(owner.id), role="owner", status="active"))
    await db.flush()
    token = create_access_token(
        {
            "sub": owner.username,
            "staff_user_id": owner.id,
            "auth_version": owner.auth_version,
            "auth_source": "warranty-policy-series-api-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_warranty_policy_api_supports_multi_series_and_legacy_updates(
    async_client: AsyncClient,
    db,
):
    headers = await _owner_headers(db)
    supplier = Supplier(name="Warranty API supplier", code="warranty-api-supplier")
    brand = Brand(title="Warranty API brand", slug="warranty-api-brand")
    other_brand = Brand(title="Other warranty brand", slug="other-warranty-api-brand")
    db.add_all([supplier, brand, other_brand])
    await db.flush()
    first = ProductSeries(brand_id=brand.id, title="First API series", slug="first-warranty-api-series")
    second = ProductSeries(brand_id=brand.id, title="Second API series", slug="second-warranty-api-series")
    foreign = ProductSeries(brand_id=other_brand.id, title="Foreign API series", slug="foreign-warranty-api-series")
    db.add_all([first, second, foreign])
    await db.commit()

    created = await async_client.post(
        "/api/manager/warranty-policies",
        headers=headers,
        json={
            "name": "Selected series policy",
            "supplier_id": supplier.id,
            "brand_id": brand.id,
            "series_ids": [first.id, second.id],
            "duration_months": 48,
            "maintenance_required": True,
        },
    )
    assert created.status_code == 201
    item = created.json()
    assert item["series_id"] == first.id
    assert item["series_ids"] == [first.id, second.id]
    assert item["series_titles"] == ["First API series", "Second API series"]
    assert item["series_brand_id"] == brand.id
    assert item["maintenance_interval_months"] == 12

    retained = await async_client.patch(
        f"/api/manager/warranty-policies/{item['id']}",
        headers=headers,
        json={"name": "Retained selection"},
    )
    assert retained.status_code == 200
    assert retained.json()["series_ids"] == [first.id, second.id]

    rejected = await async_client.patch(
        f"/api/manager/warranty-policies/{item['id']}",
        headers=headers,
        json={"series_ids": [first.id, foreign.id]},
    )
    assert rejected.status_code == 400
    assert "one brand" in rejected.json()["detail"]
    listed = await async_client.get("/api/manager/warranty-policies", headers=headers)
    assert listed.status_code == 200
    unchanged = next(row for row in listed.json()["items"] if row["id"] == item["id"])
    assert unchanged["series_ids"] == [first.id, second.id]

    legacy_write = await async_client.patch(
        f"/api/manager/warranty-policies/{item['id']}",
        headers=headers,
        json={"series_id": second.id},
    )
    assert legacy_write.status_code == 200
    assert legacy_write.json()["series_id"] == second.id
    assert legacy_write.json()["series_ids"] == [second.id]
