"""Exercise real identities, company visibility, optimistic writes and live revocation."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from api_contracts.manager_platform_companies import PlatformCompanyUpdate
from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, create_access_token
from models import LegacyOwnerAuthState, StaffUser, Storefront, StorefrontDomain, Tenant, TenantAuditEvent, TenantMembership
from routers.manager_platform_companies import router
from services.manager_capability_service import ManagerCapabilityService


def token(staff_id, username, **claims):
    value = create_access_token({"sub": username, "staff_user_id": staff_id,
        "auth_source": "staff_password", "auth_version": 1, **claims})
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
async def companies_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'companies.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
            Tenant(id=2, slug="partner", display_name="Partner"),
            Tenant(id=3, slug="disabled", display_name="Disabled", status="disabled", demo_read_only=True),
            Storefront(id=1, tenant_id=1, slug="main", display_name="MVN", status="active", is_default=True),
            Storefront(id=2, tenant_id=2, slug="main", display_name="Partner", status="active", is_default=True),
            Storefront(id=3, tenant_id=2, slug="draft", display_name="Draft", status="draft"),
            Storefront(id=4, tenant_id=3, slug="main", display_name="Disabled site", status="disabled", is_default=True),
            StaffUser(id=10, username=settings.ADMIN_USERNAME, display_name="Platform owner", roles=["owner"], primary_role="owner"),
            StaffUser(id=11, username="partner-owner", display_name="Partner owner", roles=["owner"], primary_role="owner"),
            StaffUser(id=12, username="disabled-person", display_name="Inactive", status="inactive", roles=["manager"], primary_role="manager"),
        ])
        await session.flush()
        session.add_all([
            LegacyOwnerAuthState(mode="staff_shadow", owner_staff_user_id=10),
            TenantMembership(tenant_id=1, staff_user_id=10, role="owner"),
            TenantMembership(tenant_id=2, staff_user_id=11, role="owner"),
            TenantMembership(tenant_id=2, staff_user_id=12, role="manager"),
            StorefrontDomain(storefront_id=2, hostname="partner.example", status="active", is_primary=True,
                             verified_at=datetime.now(timezone.utc)),
            StorefrontDomain(storefront_id=3, hostname="draft.example", status="pending"),
        ])
        await session.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_session] = lambda: session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield session, client, token(10, settings.ADMIN_USERNAME), token(11, "partner-owner")
    await engine.dispose()


@pytest.mark.asyncio
async def test_platform_directory_includes_disabled_and_draft_without_credentials(companies_context):
    _, client, owner, partner = companies_context
    response = await client.get("/api/manager/platform/companies", headers={**owner,
        "X-MVN-Manager-Tenant": "invalid-stale-header", "X-MVN-Manager-Storefront": "missing"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3 and len(body["items"]) == 3
    company = next(item for item in body["items"] if item["id"] == 2)
    assert company["owners"] == [{"staff_user_id": 11, "display_name": "Partner owner"}]
    assert company["active_staff_count"] == 1
    assert {site["status"] for site in company["sites"]} == {"active", "draft"}
    assert {domain["hostname"] for site in company["sites"] for domain in site["domains"]} == {"partner.example", "draft.example"}
    assert all(secret not in response.text for secret in ("password_hash", "telegram_id", "auth_version"))
    assert (await client.get("/api/manager/platform/companies", headers=partner)).status_code == 403
    forged = token(11, "partner-owner", is_platform_owner=True, role="owner")
    assert (await client.get("/api/manager/platform/companies", headers=forged)).status_code == 403
    page = await client.get("/api/manager/platform/companies?limit=1&page=2", headers=owner)
    assert page.status_code == 200 and len(page.json()["items"]) == 1 and page.json()["total"] == 3
    search = await client.get("/api/manager/platform/companies?search=partner", headers=owner)
    assert search.status_code == 200 and search.json()["total"] == 1
    assert (await client.get("/api/manager/platform/companies?limit=101", headers=owner)).status_code == 422


@pytest.mark.asyncio
async def test_company_owner_sees_only_own_sites_including_unpublished(companies_context):
    _, client, _, partner = companies_context
    response = await client.get("/api/manager/company/sites", headers=partner)
    assert response.status_code == 200, response.text
    assert {site["id"] for site in response.json()["items"]} == {2, 3}
    page = await client.get("/api/manager/company/sites?limit=1&page=2", headers=partner)
    assert page.status_code == 200 and len(page.json()["items"]) == 1 and page.json()["total"] == 2
    assert (await client.get("/api/manager/company/sites?limit=101", headers=partner)).status_code == 422
    denied = await client.get("/api/manager/company/sites", headers={**partner, "X-MVN-Manager-Tenant": "1"})
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_company_write_is_optimistic_audited_and_disables_access_live(companies_context):
    session, client, owner, partner = companies_context
    company = (await client.get("/api/manager/platform/companies?search=partner", headers=owner)).json()["items"][0]
    url = "/api/manager/platform/companies/2"
    payload = {"expected_updated_at": company["updated_at"], "display_name": "Updated partner", "status": "disabled"}
    for extra in ({}, {"X-Kitlane-Team": "1", "Origin": "https://hostile.example"}):
        assert (await client.patch(url, headers={**owner, **extra}, json=payload)).status_code == 403
    headers = {**owner, "X-Kitlane-Team": "1"}
    updated = await client.patch(url, headers=headers, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Updated partner" and updated.json()["status"] == "disabled"
    audit = (await session.scalars(select(TenantAuditEvent))).one()
    assert audit.tenant_id == 2 and audit.storefront_id == 2 and audit.actor_staff_user_id == 10
    assert audit.action == "company.updated" and set(audit.change_set) == {"display_name", "status"}
    assert (await client.patch(url, headers=headers, json=payload)).status_code == 409
    assert (await client.get("/api/manager/company/sites", headers=partner)).status_code == 403
    restored = await client.patch(url, headers=headers, json={"expected_updated_at": updated.json()["updated_at"], "status": "active"})
    assert restored.status_code == 200
    assert (await client.get("/api/manager/company/sites", headers=partner)).status_code == 200


@pytest.mark.asyncio
async def test_system_company_and_revoked_platform_identity_are_protected(companies_context):
    session, client, owner, _ = companies_context
    company = (await client.get("/api/manager/platform/companies?search=mvn", headers=owner)).json()["items"][0]
    response = await client.patch("/api/manager/platform/companies/1", headers={**owner, "X-Kitlane-Team": "1"},
        json={"expected_updated_at": company["updated_at"], "status": "disabled"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "system_company_protected"
    user = await session.get(StaffUser, 10)
    user.auth_version += 1
    session.add(user)
    await session.commit()
    assert (await client.get("/api/manager/platform/companies", headers=owner)).status_code == 401


@pytest.mark.parametrize("changes", [{}, {"status": None}, {"display_name": "   "}, {"slug": "other"}, {"demo_read_only": True}])
def test_company_update_rejects_missing_null_and_provisioning_fields(changes):
    with pytest.raises(ValidationError):
        PlatformCompanyUpdate(expected_updated_at=datetime.now(timezone.utc), **changes)


def test_platform_company_capability_survives_support_context_without_global_tools():
    auth = AuthenticatedUser(username="owner", auth_source="test", role="owner", tenant_id=2,
                             storefront_id=2, is_platform_owner=True)
    caps = ManagerCapabilityService.for_auth(auth)
    assert "platform.companies.manage" in caps
    assert "platform.manage" not in caps and "infrastructure.manage" not in caps
    assert "platform.companies.manage" not in ManagerCapabilityService.for_auth(replace(auth, is_platform_owner=False))
