from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from starlette.requests import Request

from core.config import settings
from core.security import create_access_token, get_current_auth_context
from models import Installer, LegacyOwnerAuthState, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.staff_avatar import StaffAvatar
from services.connector_auth_service import ConnectorAuthService
from services.credential_service import CredentialService
from services.legacy_owner_cutover_service import LegacyOwnerCutoverService, LegacyOwnerCutoverBlockedError
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.owner_profile_consolidation_service import OwnerProfileConsolidationService as Service
from services.legacy_owner_profile_policy import LegacyOwnerProfilePolicy


async def seed(session):
    if await session.get(Tenant, 1) is None:
        session.add(Tenant(id=1, slug="mvn", display_name="MVN", is_system=True))
    if await session.get(Storefront, 1) is None:
        session.add(Storefront(id=1, tenant_id=1, slug="main", display_name="Main", status="active", is_default=True))
    session.add(Installer(id=1, name="Vadim", telegram_id=12345))
    await session.flush()
    session.add(StaffUser(id=1, display_name="Vadim", primary_role="owner", roles=["owner", "installer"],
                          legacy_installer_id=1, telegram_id=12345, auth_version=3, phone="private-phone"))
    session.add(StaffUser(id=4, display_name="System Owner", primary_role="owner", roles=["owner"],
                          username=settings.ADMIN_USERNAME, password_hash=CredentialService.hash_password("target-password"),
                          auth_version=8, password_changed_at=datetime.now(timezone.utc)))
    await session.flush()
    session.add_all([TenantMembership(id=1, tenant_id=1, staff_user_id=1, role="owner"),
                     TenantMembership(id=4, tenant_id=1, staff_user_id=4, role="owner")])
    state = await session.get(LegacyOwnerAuthState, 1)
    if state is None:
        state = LegacyOwnerAuthState(id=1)
    state.mode, state.owner_staff_user_id, state.legacy_token_version = "staff_shadow", 4, 2
    session.add(state)
    await session.commit()


@pytest.fixture
async def owner_session(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'owner.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    monkeypatch.setattr(LegacyOwnerCutoverService, "_try_acquire_advisory_lock", AsyncMock(return_value=True))
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await seed(session)
        yield session
    await engine.dispose()


async def auth(session, user_id, username, version):
    token = create_access_token({"sub": username, "staff_user_id": user_id, "auth_version": version})
    return await get_current_auth_context(Request({"type": "http", "method": "GET", "headers": []}), token, session)


@pytest.mark.asyncio
async def test_consolidation_preserves_owner_sessions_and_connector_identity(owner_session):
    session = owner_session
    target = await session.get(StaffUser, 4)
    original_hash = target.password_hash
    snapshot = SimpleNamespace(staff_user_id=4, auth_version=8, membership_id=4, tenant_id=1, storefront_id=1, role="owner", scopes=[])
    assert (await auth(session, 4, settings.ADMIN_USERNAME, 8)).is_platform_owner
    assert (await auth(session, 1, "12345", 3)).staff_user_id == 1
    assert (await ConnectorAuthService._live_actor(session, snapshot)).staff_user_id == 4
    plan = await Service.plan(session)
    assert plan["ready"], plan
    assert "private-phone" not in str(plan)
    assert original_hash not in str(plan)
    result = await Service.execute(session, plan_token=plan["plan_token"])
    await session.commit()
    assert result["complete"] and result["changed"]
    await session.refresh(target)
    source = await session.get(StaffUser, 1)
    assert (target.password_hash, target.auth_version, target.username) == (original_hash, 8, settings.ADMIN_USERNAME)
    assert (target.telegram_id, target.legacy_installer_id, target.display_name) == (12345, 1, "Vadim")
    assert target.telegram_verified_at is not None
    assert source.merged_into_staff_user_id == 4 and source.status == "inactive" and source.auth_version == 4
    with pytest.raises(HTTPException) as exc:
        await auth(session, 1, "12345", 3)
    assert exc.value.status_code == 401
    assert (await auth(session, 4, settings.ADMIN_USERNAME, 8)).is_platform_owner
    assert (await auth(session, 4, "12345", 8)).is_platform_owner
    assert (await ConnectorAuthService._live_actor(session, snapshot)).staff_user_id == 4
    assert await LegacyOwnerManagedIdentityService.telegram_login_allowed(session, telegram_id=12345)
    rollback = await LegacyOwnerCutoverService.plan(session, for_action="rollback")
    assert rollback["ready"], rollback
    await LegacyOwnerCutoverService.rollback(session, plan_token=rollback["plan_token"])
    await session.commit()
    assert source.merged_into_staff_user_id == 4 and target.telegram_id == 12345
    with pytest.raises(HTTPException):
        await auth(session, 4, settings.ADMIN_USERNAME, 8)
    state = await session.get(LegacyOwnerAuthState, 1)
    assert state.mode == "legacy" and state.owner_staff_user_id == 4


@pytest.mark.asyncio
async def test_stale_profile_plan_does_not_mutate(owner_session):
    plan = await Service.plan(owner_session)
    target = await owner_session.get(StaffUser, 4)
    target.phone = "new-value"
    await owner_session.commit()
    with pytest.raises(LegacyOwnerCutoverBlockedError, match="stale"):
        await Service.execute(owner_session, plan_token=plan["plan_token"])
    assert (await owner_session.get(StaffUser, 1)).status == "active"


@pytest.mark.asyncio
async def test_new_source_business_reference_blocks_plan(owner_session):
    from models.personal_task import PersonalTask
    owner_session.add(PersonalTask(tenant_id=1, storefront_id=1, author_staff_user_id=1, text="Unreviewed work"))
    await owner_session.commit()
    plan = await Service.plan(owner_session)
    assert not plan["ready"]
    assert "source_references_require_review" in plan["blockers"]


@pytest.mark.asyncio
async def test_avatar_transfer_is_atomic_and_repeat_is_noop(owner_session):
    source = await owner_session.get(StaffUser, 1)
    source.avatar_version = "a" * 64
    owner_session.add(StaffAvatar(staff_user_id=1, content=b"photo", content_hash="a" * 64))
    await owner_session.commit()
    plan = await Service.plan(owner_session)
    await Service.execute(owner_session, plan_token=plan["plan_token"])
    await owner_session.commit()
    assert await owner_session.get(StaffAvatar, 1) is None
    assert (await owner_session.get(StaffAvatar, 4)).content == b"photo"
    plan = await Service.plan(owner_session)
    result = await Service.execute(owner_session, plan_token=plan["plan_token"])
    assert not result["changed"]
    events = list((await owner_session.execute(select(TenantAuditEvent).where(TenantAuditEvent.action == Service.ACTION))).scalars())
    assert len(events) == 1


@pytest.mark.asyncio
async def test_failure_after_unique_transfer_rolls_back(owner_session, monkeypatch):
    plan = await Service.plan(owner_session)
    original = Service._load.__func__
    async def failed_postcheck(cls, session, *, lock=False):
        if not lock:
            raise RuntimeError("post-check failure")
        return await original(cls, session, lock=lock)
    monkeypatch.setattr(Service, "_load", classmethod(failed_postcheck))
    with pytest.raises(RuntimeError):
        await Service.execute(owner_session, plan_token=plan["plan_token"])
    await owner_session.rollback()
    source, target = await owner_session.get(StaffUser, 1), await owner_session.get(StaffUser, 4)
    assert source.telegram_id == 12345 and source.legacy_installer_id == 1 and source.status == "active"
    assert target.telegram_id is None and target.legacy_installer_id is None and target.auth_version == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("source_consent,target_consent", [(False, True), (True, False), (False, False)])
async def test_consolidation_preserves_either_notification_optout(owner_session, source_consent, target_consent):
    source, target = await owner_session.get(StaffUser, 1), await owner_session.get(StaffUser, 4)
    source.telegram_notifications_enabled = source_consent
    target.telegram_notifications_enabled = target_consent
    await owner_session.commit()
    plan = await Service.plan(owner_session)
    await Service.execute(owner_session, plan_token=plan["plan_token"])
    assert target.telegram_notifications_enabled is False


@pytest.mark.asyncio
async def test_bound_owner_tokens_fail_closed_on_invalid_linked_profile(owner_session):
    target = await owner_session.get(StaffUser, 4)
    target.telegram_id = 54321
    await owner_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth(owner_session, 4, settings.ADMIN_USERNAME, 8)
    assert exc.value.status_code == 401
    target.telegram_verified_at = datetime.now(timezone.utc)
    await owner_session.commit()
    assert (await auth(owner_session, 4, settings.ADMIN_USERNAME, 8)).is_platform_owner
    target.roles = ["owner", "installer"]
    await owner_session.commit()
    with pytest.raises(HTTPException):
        await auth(owner_session, 4, settings.ADMIN_USERNAME, 8)


def test_installer_owner_requires_consistent_verified_identity():
    owner = StaffUser(id=4, display_name="Owner", status="active", primary_role="owner", roles=["owner", "installer"],
                      legacy_installer_id=1, telegram_id=10, telegram_verified_at=datetime.now(timezone.utc))
    installer = Installer(id=1, name="Owner", telegram_id=10)
    assert LegacyOwnerProfilePolicy.allows(owner, installer=installer)
    installer.telegram_id = 11
    assert not LegacyOwnerProfilePolicy.allows(owner, installer=installer)
    installer.telegram_id = 10
    owner.telegram_verified_at = None
    assert not LegacyOwnerProfilePolicy.allows(owner, installer=installer)
