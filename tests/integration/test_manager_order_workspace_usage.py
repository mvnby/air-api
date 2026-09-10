import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from core.security import create_access_token
from models import OrderWorkspaceUsageDaily, StaffUser, Storefront, Tenant, TenantMembership
from models.tenancy import TenantScope
from schemas_order_usage import OrderUsageBatch
from services.manager_storefront_selector_service import MANAGER_STOREFRONT_HEADER
from services.order_workspace_usage_service import OrderWorkspaceUsageService, USAGE_TIMEZONE


BASE = "/api/manager/order-workspace-usage"
EVENT = dict(metric="product_add", workflow="maintenance", party_kind="company", viewport="desktop")


async def _staff(db, tenant_id, username, role="owner"):
    staff = StaffUser(display_name=username, username=username, status="active", roles=[role], primary_role=role)
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=tenant_id, staff_user_id=staff.id, role=role, status="active"))
    await db.flush()
    return staff


def _headers(staff, slug="main"):
    token = create_access_token({
        "sub": staff.username, "staff_user_id": staff.id,
        "auth_version": staff.auth_version, "auth_source": "order-usage-test",
    }, expires_delta=timedelta(minutes=10))
    return {"Authorization": f"Bearer {token}", MANAGER_STOREFRONT_HEADER: slug}


@pytest.mark.asyncio
async def test_usage_api_aggregates_with_exact_tenant_storefront_and_owner_report_access(async_client, db):
    db.add(Tenant(id=2, slug="usage-tenant", display_name="Other", status="active", is_system=False))
    await db.flush()
    db.add_all([
        Storefront(id=2, tenant_id=1, slug="orsha", display_name="Orsha", status="active", is_default=False),
        Storefront(id=3, tenant_id=2, slug="main", display_name="Other main", status="active", is_default=True),
    ])
    owner = await _staff(db, 1, "usage-owner")
    manager = await _staff(db, 1, "usage-manager", "manager")
    foreign_owner = await _staff(db, 2, "usage-foreign-owner")
    await db.commit()

    assert (await async_client.post(f"{BASE}/batch", json={"events": [EVENT]})).status_code == 401
    for staff, slug, count in [(manager, "main", 2), (owner, "orsha", 3), (foreign_owner, "main", 4)]:
        response = await async_client.post(f"{BASE}/batch", headers=_headers(staff, slug), json={"events": [EVENT] * count})
        assert response.status_code == 200, response.text
        assert response.json() == {"accepted": count}
    # A later batch must increment the same bucket, never replace its count.
    response = await async_client.post(f"{BASE}/batch", headers=_headers(owner), json={"events": [EVENT]})
    assert response.status_code == 200

    assert (await async_client.get(f"{BASE}/daily", headers=_headers(manager))).status_code == 403
    for staff, slug, count in [(owner, "main", 3), (owner, "orsha", 3), (foreign_owner, "main", 4)]:
        report = await async_client.get(f"{BASE}/daily", headers=_headers(staff, slug))
        assert report.status_code == 200, report.text
        result = report.json()
        assert result["timezone"] == "Europe/Minsk"
        assert len(result["items"]) == 1
        assert result["items"][0]["count"] == count
        assert set(result["items"][0]) == {"day", "count", *EVENT.keys()}
    filtered = await async_client.get(f"{BASE}/daily?workflow=repair", headers=_headers(owner))
    assert filtered.json()["items"] == []
    denied = await async_client.get(f"{BASE}/daily", headers=_headers(foreign_owner, "orsha"))
    assert denied.status_code == 403
    for query in ("days=0", "days=91", "viewport=anything", "party_kind=private-text"):
        assert (await async_client.get(f"{BASE}/daily?{query}", headers=_headers(owner))).status_code == 422
    for payload in ({"events": [{**EVENT, "customer_id": 9}]}, {"events": [EVENT], "tenant_id": 2}):
        assert (await async_client.post(f"{BASE}/batch", headers=_headers(owner), json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_concurrent_usage_batches_do_not_lose_increments(db_engine):
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    payload = OrderUsageBatch.model_validate({"events": [EVENT] * 5})

    async def send():
        async with sessions() as session:
            return await OrderWorkspaceUsageService.record(session, scope, payload)

    assert await asyncio.gather(*(send() for _ in range(8))) == [5] * 8
    async with sessions() as session:
        report = await OrderWorkspaceUsageService.report(session, scope, days=1)
        assert len(report.items) == 1
        assert report.items[0].count == 40


@pytest.mark.asyncio
async def test_record_prunes_only_current_scope_and_report_excludes_expired_and_future_days(db, monkeypatch):
    today = datetime.now(USAGE_TIMEZONE).date()
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)
    db.add(Storefront(id=2, tenant_id=1, slug="orsha", display_name="Orsha", status="active", is_default=False))
    await db.flush()
    for storefront_id, age, metric in [(1, 90, "order_open"), (1, 89, "documents_open"), (1, -1, "work_open"), (2, 90, "order_open")]:
        db.add(OrderWorkspaceUsageDaily(
            tenant_id=1, storefront_id=storefront_id, day=today - timedelta(days=age),
            layout_version="workspace_v1", **{**EVENT, "metric": metric}, count=2,
        ))
    await db.commit()
    await OrderWorkspaceUsageService.record(db, scope, OrderUsageBatch.model_validate({"events": [EVENT]}))
    rows = list((await db.execute(select(OrderWorkspaceUsageDaily))).scalars())
    assert {(row.storefront_id, row.metric) for row in rows} == {(1, "documents_open"), (1, "work_open"), (1, "product_add"), (2, "order_open")}
    report = await OrderWorkspaceUsageService.report(db, scope, days=90)
    assert {item.metric for item in report.items} == {"documents_open", "product_add"}
