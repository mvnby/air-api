import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from core.security import create_access_token
from models import CatalogWorkspaceUsageDaily, StaffUser, TenantMembership
from schemas_catalog_usage import CatalogUsageBatch
from services.catalog_workspace_usage_service import CatalogWorkspaceUsageService


BASE = "/api/manager/catalog-usage"
EVENT = dict(device="desktop", action="edit_gallery", outcome="success", duration_bucket="1_3s")


async def _staff(db, username, role):
    staff = StaffUser(display_name=username, username=username, status="active", roles=[role], primary_role=role)
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role=role, status="active"))
    await db.flush()
    return staff


def _headers(staff):
    token = create_access_token({"sub": staff.username, "staff_user_id": staff.id, "auth_version": staff.auth_version, "auth_source": "catalog-usage-test"}, expires_delta=timedelta(minutes=10))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_catalog_usage_is_platform_only_and_report_requires_analytics_manage(async_client, db):
    owner = await _staff(db, "catalog-usage-owner", "owner")
    manager = await _staff(db, "catalog-usage-manager", "manager")
    await db.commit()

    assert (await async_client.post(f"{BASE}/batch", json={"events": [EVENT]})).status_code == 401
    assert (await async_client.post(f"{BASE}/batch", headers=_headers(manager), json={"events": [EVENT]})).status_code == 200
    assert (await async_client.get(f"{BASE}/daily", headers=_headers(manager))).status_code == 403
    report = await async_client.get(f"{BASE}/daily?days=90", headers=_headers(owner))
    assert report.status_code == 200, report.text
    result = report.json()
    assert result["timezone"] == "Europe/Minsk"
    assert result["items"][0]["count"] == 1
    assert set(result["items"][0]) == {"day", "layout_version", "device", "action", "outcome", "duration_bucket", "count"}
    for query in ("days=0", "days=91", "action=private-text", "device=1920x1080"):
        assert (await async_client.get(f"{BASE}/daily?{query}", headers=_headers(owner))).status_code == 422
    for payload in ({"events": [{**EVENT, "product_id": 3}]}, {"events": [EVENT], "pilot_opt_in": False}):
        assert (await async_client.post(f"{BASE}/batch", headers=_headers(owner), json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_catalog_usage_concurrent_batches_increment_one_anonymous_bucket(db_engine):
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    payload = CatalogUsageBatch.model_validate({"events": [EVENT] * 5})

    async def send():
        async with sessions() as session:
            return await CatalogWorkspaceUsageService.record(session, payload)

    assert await asyncio.gather(*(send() for _ in range(8))) == [5] * 8
    async with sessions() as session:
        report = await CatalogWorkspaceUsageService.report(session, days=1)
        assert len(report.items) == 1
        assert report.items[0].count == 40
        row = (await session.execute(select(CatalogWorkspaceUsageDaily))).scalars().one()
        assert not hasattr(row, "tenant_id")
