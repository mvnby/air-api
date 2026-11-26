from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel, select

from core.security import AuthenticatedIdentity, AuthenticatedUser
from crud.tender_module import TenderModuleDAO
from models import Storefront, Tenant, TenantAuditEvent, TenantTenderModule
from schemas_tender_search import TenderModuleEntitlementUpdate, TenderModuleUpdate, TenderSearchProfile
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.tender_module_service import TenderModuleError, TenderModuleService as Modules


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(lambda db: SQLModel.metadata.create_all(
            db, tables=[Tenant.__table__, Storefront.__table__, TenantTenderModule.__table__, TenantAuditEvent.__table__],
        ))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        for company_id in (11, 12):
            session.add(Tenant(id=company_id, slug=f"company-{company_id}", display_name=f"Компания {company_id}"))
            session.add(Storefront(
                id=company_id + 10, tenant_id=company_id, slug="primary", display_name="Основной",
                status="active", is_default=True,
            ))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def platform_owner(monkeypatch):
    monkeypatch.setattr(LegacyOwnerAuthStateService, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(LegacyOwnerManagedIdentityService, "exact_bound_staff_identity_allowed",
                        AsyncMock(return_value=True))
    monkeypatch.setattr("services.tender_module_service.PlatformCompaniesDAO.lock_staff", AsyncMock(
        return_value=SimpleNamespace(id=99, status="active", merged_into_staff_user_id=None, auth_version=8),
    ))
    return AuthenticatedIdentity("platform", "jwt", staff_user_id=99, auth_version=8, is_platform_owner=True)


def owner(company_id):
    return AuthenticatedUser("owner", "jwt", tenant_id=company_id, storefront_id=company_id + 10, role="owner")


@pytest.mark.asyncio
async def test_enablement_and_search_profiles_are_company_owned(session, platform_owner):
    profile_a = TenderSearchProfile(name="Климат", excluded_directions=["ventilation", "refrigeration"])
    profile_b = TenderSearchProfile(name="Холодильное оборудование", included_directions=["refrigeration"])
    for company_id in (11, 12):
        default = await Modules.get(session, company_id)
        assert not default.enabled and not default.entitled and default.profiles == []
        grant = await Modules.set_entitlement(
            session, company_id, platform_owner, TenderModuleEntitlementUpdate(entitled=True, version=0),
        )
        assert grant.entitled and not grant.enabled and grant.version == 1
    saved_a = await Modules.update(session, owner(11), TenderModuleUpdate(enabled=True, version=1, profiles=[profile_a]))
    saved_b = await Modules.update(session, owner(12), TenderModuleUpdate(enabled=True, version=1, profiles=[profile_b]))
    assert saved_a.enabled and saved_a.version == 2
    assert saved_b.enabled and saved_b.version == 2
    assert (await Modules.get(session, 11)).profiles == [profile_a]
    assert (await Modules.get(session, 12)).profiles == [profile_b]
    audit = (await session.scalars(select(TenantAuditEvent).order_by(TenantAuditEvent.id))).all()
    assert [(event.tenant_id, event.storefront_id, event.action) for event in audit] == [
        (11, 21, "tender_module.entitlement.updated"), (12, 22, "tender_module.entitlement.updated"),
        (11, 21, "tender_module.settings.updated"), (12, 22, "tender_module.settings.updated"),
    ]


@pytest.mark.asyncio
async def test_revocation_is_immediate_preserves_profiles_and_rejects_stale_writes(session, platform_owner):
    profile = TenderSearchProfile(name="Вся Беларусь")
    payload = TenderModuleUpdate(enabled=True, version=0, profiles=[profile])
    with pytest.raises(TenderModuleError) as unauthorized:
        await Modules.update(session, owner(11), payload)
    assert unauthorized.value.status_code == 403
    await Modules.set_entitlement(session, 11, platform_owner, TenderModuleEntitlementUpdate(entitled=True, version=0))
    current = await Modules.update(session, owner(11), payload.model_copy(update={"version": 1}))
    with pytest.raises(TenderModuleError) as stale:
        await Modules.update(session, owner(11), payload.model_copy(update={"version": 1}))
    assert stale.value.status_code == 409
    revoked = await Modules.set_entitlement(
        session, 11, platform_owner, TenderModuleEntitlementUpdate(entitled=False, version=current.version),
    )
    assert not revoked.enabled and not revoked.entitled and revoked.profiles == [profile]
    regranted = await Modules.set_entitlement(
        session, 11, platform_owner, TenderModuleEntitlementUpdate(entitled=True, version=revoked.version),
    )
    assert regranted.entitled and not regranted.enabled and regranted.profiles == [profile]


@pytest.mark.asyncio
async def test_preview_query_limits_tenders_to_the_selected_company_and_storefront():
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(all=lambda: [])))
    assert await TenderModuleDAO.recent_orders(session, owner(11).tenant_scope()) == []
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    assert '"order".tenant_id = 11' in str(query)
    assert '"order".storefront_id = 21' in str(query)
    assert '"order".lead_source = ' in str(query)
    assert "LIMIT 20" in str(query)
