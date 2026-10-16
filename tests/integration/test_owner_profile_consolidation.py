"""Physical PostgreSQL proves owner transition uniqueness and lock fencing."""

from datetime import datetime, timezone
import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import settings
from models import Installer, LegacyOwnerAuthState, StaffUser, TenantMembership
from services.credential_service import CredentialService
from services.legacy_owner_cutover_service import LegacyOwnerCutoverBlockedError
from services.owner_profile_consolidation_service import OwnerProfileConsolidationService as Service


async def seed(db):
    db.add(Installer(id=1, name="Person", telegram_id=991234))
    await db.flush()
    db.add_all([
        StaffUser(id=1, display_name="Person", primary_role="owner", roles=["owner", "installer"],
                  telegram_id=991234, legacy_installer_id=1),
        StaffUser(id=4, display_name="Bootstrap", primary_role="owner", roles=["owner"],
                  username=settings.ADMIN_USERNAME, password_hash=CredentialService.hash_password("owner-password"),
                  password_changed_at=datetime.now(timezone.utc)),
    ])
    await db.flush()
    db.add_all([TenantMembership(tenant_id=1, staff_user_id=1, role="owner"),
                TenantMembership(tenant_id=1, staff_user_id=4, role="owner")])
    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode, state.owner_staff_user_id = "staff_shadow", 4
    await db.commit()


@pytest.mark.asyncio
async def test_postgres_unique_transfers_and_competing_owner_operation(db_engine):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    # The db fixture deliberately retains an outer rollback transaction.
    # Independent connections require fully committed seed rows instead.
    async with factory() as setup:
        await seed(setup)
        plan = await Service.plan(setup)
        assert plan["ready"], plan
    async with factory() as first, factory() as second:
        result = await asyncio.wait_for(Service.execute(first, plan_token=plan["plan_token"]), timeout=15)
        assert result["complete"]
        with pytest.raises(LegacyOwnerCutoverBlockedError, match="owns the lock"):
            await asyncio.wait_for(Service.execute(second, plan_token=plan["plan_token"]), timeout=15)
        await second.rollback()
        # A commit makes the unique transfer durable; the old source no longer
        # owns either key, and retrying its reviewed plan is stale.
        await first.commit()
        with pytest.raises(LegacyOwnerCutoverBlockedError, match="stale"):
            await asyncio.wait_for(Service.execute(second, plan_token=plan["plan_token"]), timeout=15)
        await second.rollback()
        source, target = await second.get(StaffUser, 1), await second.get(StaffUser, 4)
        assert source.telegram_id is None and source.legacy_installer_id is None
        assert target.telegram_id == 991234 and target.legacy_installer_id == 1
        assert source.status == "inactive" and source.merged_into_staff_user_id == 4


@pytest.mark.asyncio
async def test_postgres_failed_transition_releases_unique_keys_without_partial_merge(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        await seed(setup)
        plan = await Service.plan(setup)
        assert plan["ready"], plan
    original = Service._load.__func__
    async def fail_postcheck(cls, session, *, lock=False):
        if not lock:
            raise RuntimeError("post-check failed")
        return await original(cls, session, lock=lock)
    monkeypatch.setattr(Service, "_load", classmethod(fail_postcheck))
    async with factory() as writer:
        with pytest.raises(RuntimeError):
            await asyncio.wait_for(Service.execute(writer, plan_token=plan["plan_token"]), timeout=15)
        await writer.rollback()
    async with factory() as reader:
        source, target = await reader.get(StaffUser, 1), await reader.get(StaffUser, 4)
        assert source.telegram_id == 991234 and source.legacy_installer_id == 1
        assert source.status == "active" and source.merged_into_staff_user_id is None
        assert target.telegram_id is None and target.legacy_installer_id is None
