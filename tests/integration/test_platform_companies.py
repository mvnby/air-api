"""Independent committed PostgreSQL connections prove company write fencing."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api_contracts.manager_platform_companies import PlatformCompanyUpdate
from core.config import settings
from core.security import AuthenticatedIdentity
from models import LegacyOwnerAuthState, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.platform_companies_service import PlatformCompaniesService, PlatformCompanyError


async def seed(factory):
    async with factory() as session:
        owner = StaffUser(username=settings.ADMIN_USERNAME, display_name="Owner", roles=["owner"], primary_role="owner")
        company = Tenant(slug="company-write-test", display_name="Partner")
        session.add_all([owner, company])
        await session.flush()
        session.add_all([TenantMembership(tenant_id=1, staff_user_id=owner.id, role="owner"),
            Storefront(tenant_id=company.id, slug="main", display_name="Partner", is_default=True, status="active")])
        state = await session.get(LegacyOwnerAuthState, 1)
        state.mode, state.owner_staff_user_id = "staff_shadow", owner.id
        await session.commit()
        actor = AuthenticatedIdentity(username=owner.username, auth_source="staff_password",
            staff_user_id=owner.id, auth_version=owner.auth_version, is_platform_owner=True)
        return actor, company.id, company.updated_at


@pytest.mark.asyncio
async def test_concurrent_company_updates_accept_only_one_timestamp(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    actor, tenant_id, expected = await seed(factory)

    async def update(name):
        async with factory() as session:
            try:
                result = await PlatformCompaniesService.update(session, tenant_id=tenant_id,
                    payload=PlatformCompanyUpdate(expected_updated_at=expected, display_name=name), actor=actor)
                return result.display_name
            except PlatformCompanyError as error:
                await session.rollback()
                return error.code

    results = await asyncio.wait_for(asyncio.gather(update("First"), update("Second")), timeout=15)
    assert results.count("company_changed") == 1
    async with factory() as session:
        company = await session.get(Tenant, tenant_id)
        assert company.display_name in {"First", "Second"}
        audits = list((await session.scalars(select(TenantAuditEvent).where(TenantAuditEvent.action == "company.updated"))).all())
        assert len(audits) == 1 and audits[0].tenant_id == tenant_id


@pytest.mark.asyncio
async def test_platform_credential_revoked_while_waiting_cannot_mutate_company(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    actor, tenant_id, expected = await seed(factory)
    async with factory() as revoker, factory() as writer:
        await LegacyOwnerAuthStateService.get(revoker, for_update=True)
        owner = await revoker.get(StaffUser, actor.staff_user_id)
        owner.auth_version += 1
        revoker.add(owner)
        await revoker.flush()
        operation = asyncio.create_task(PlatformCompaniesService.update(writer, tenant_id=tenant_id,
            payload=PlatformCompanyUpdate(expected_updated_at=expected, display_name="Forbidden"), actor=actor))
        try:
            await asyncio.sleep(0.1)
            assert not operation.done()
            await revoker.commit()
            with pytest.raises(PlatformCompanyError) as caught:
                await asyncio.wait_for(operation, timeout=15)
            assert caught.value.code == "platform_access_changed"
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
            await writer.rollback()
    async with factory() as session:
        assert (await session.get(Tenant, tenant_id)).display_name == "Partner"
        assert not list((await session.scalars(select(TenantAuditEvent).where(TenantAuditEvent.action == "company.updated"))).all())
