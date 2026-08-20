from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from models import (
    LegacyOwnerAuthState,
    StaffUser,
    Storefront,
    Tenant,
    TenantAuditEvent,
    TenantMembership,
)
from services.credential_service import CredentialService
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_cutover_service import (
    LegacyOwnerCutoverBlockedError,
    LegacyOwnerCutoverService,
)


CUTOVER_PASSWORD = "one-time-owner-password-2026"


async def _state(db) -> LegacyOwnerAuthState:
    return await db.get(LegacyOwnerAuthState, 1)


async def _seed_bound_owner(
    db,
    *,
    telegram_id: int | None = None,
    telegram_username: str | None = None,
) -> StaffUser:
    user = StaffUser(
        display_name="System Owner",
        status="active",
        primary_role="owner",
        roles=["owner"],
        username=settings.ADMIN_USERNAME,
        password_hash=CredentialService.hash_password(settings.ADMIN_PASSWORD),
        auth_version=1,
        password_changed_at=datetime.now(timezone.utc),
        must_change_password=False,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(user.id),
            role="owner",
            status="active",
        )
    )
    state = await _state(db)
    state.owner_staff_user_id = int(user.id)
    db.add(state)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_initial_legacy_verify_is_ready_without_a_bound_staff_identity(db) -> None:
    verification = await LegacyOwnerCutoverService.verify(db)
    assert verification["ready"] is True
    assert verification["auth_mode"] == "legacy"
    assert verification["staff_user_id"] is None
    assert verification["membership_id"] is None
    assert verification["credential_matches"] is True
    assert len(verification["runtime_binding"]) == 64


@pytest.mark.asyncio
async def test_cutover_is_atomic_secret_free_idempotent_and_tenant_b_unchanged(db) -> None:
    tenant_b = Tenant(
        slug="tenant-b",
        display_name="Tenant B",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(tenant_b)
    await db.flush()
    storefront_b = Storefront(
        tenant_id=int(tenant_b.id),
        slug="main",
        display_name="Tenant B",
        status="active",
        is_default=True,
    )
    db.add(storefront_b)
    await db.flush()
    tenant_b_snapshot = (tenant_b.id, tenant_b.status, storefront_b.id, storefront_b.status)

    plan = await LegacyOwnerCutoverService.plan(db)
    serialized_plan = json.dumps(plan, sort_keys=True)
    assert plan["ready"] is True
    assert plan["changes"] == [
        "create_staff_user",
        "create_active_owner_membership",
        "activate_staff_shadow",
    ]
    assert settings.ADMIN_USERNAME not in serialized_plan
    assert settings.ADMIN_PASSWORD not in serialized_plan
    assert "password_hash" not in serialized_plan
    assert "secret" not in serialized_plan.casefold()

    result = await LegacyOwnerCutoverService.execute(
        db,
        plan_token=plan["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    assert result["changed"] is True
    assert result["auth_mode"] == "staff_shadow"
    assert result["legacy_token_version"] == 2
    assert set(result) == {
        "mode", "ready", "changed", "staff_user_id", "membership_id",
        "system_tenant_id", "system_storefront_id", "auth_mode",
        "legacy_token_version", "plan_digest",
    }

    user = await db.get(StaffUser, result["staff_user_id"])
    membership = await db.get(TenantMembership, result["membership_id"])
    state = await _state(db)
    assert user.status == "active"
    assert user.primary_role == "owner"
    assert user.roles == ["owner"]
    assert user.must_change_password is False
    assert user.password_changed_at is not None
    assert CredentialService.verify_password(CUTOVER_PASSWORD, user.password_hash)
    assert not CredentialService.verify_password(
        settings.ADMIN_PASSWORD, user.password_hash
    )
    assert (membership.tenant_id, membership.role, membership.status) == (1, "owner", "active")
    assert state.owner_staff_user_id == user.id

    audit = await db.scalar(
        select(TenantAuditEvent).where(
            TenantAuditEvent.action == LegacyOwnerCutoverService.CUTOVER_AUDIT_ACTION
        )
    )
    audit_json = json.dumps(audit.change_set, sort_keys=True)
    assert audit.tenant_id == 1 and audit.storefront_id == 1
    assert settings.ADMIN_USERNAME not in audit_json
    assert settings.ADMIN_PASSWORD not in audit_json
    assert "password" not in audit_json.casefold()
    assert "hash" not in audit_json.casefold()
    assert (tenant_b.id, tenant_b.status, storefront_b.id, storefront_b.status) == tenant_b_snapshot
    assert await db.scalar(
        select(TenantMembership).where(TenantMembership.tenant_id == tenant_b.id)
    ) is None

    no_op_plan = await LegacyOwnerCutoverService.plan(db)
    no_op = await LegacyOwnerCutoverService.execute(
        db,
        plan_token=no_op_plan["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    assert no_op_plan["changes"] == []
    assert no_op["changed"] is False
    assert int(await db.scalar(select(func.count(TenantAuditEvent.id)))) == 1

    unproved = await LegacyOwnerCutoverService.verify(db)
    wrong = await LegacyOwnerCutoverService.verify(
        db, staff_credential="wrong-one-time-password"
    )
    assert unproved["ready"] is False
    assert unproved["credential_matches"] is False
    assert wrong["ready"] is False
    assert wrong["credential_matches"] is False

    verification = await LegacyOwnerCutoverService.verify(
        db, staff_credential=CUTOVER_PASSWORD
    )
    assert verification["ready"] is True
    assert verification["credential_matches"] is True
    assert len(verification["runtime_binding"]) == 64
    assert settings.ADMIN_USERNAME not in verification["runtime_binding"]
    assert settings.ADMIN_PASSWORD not in verification["runtime_binding"]
    assert verification["can_change_password"] is True
    assert verification["auth_source_staff_password"] is True
    assert verification["legacy_jwt_rejected"] is True
    assert verification["legacy_google_auth_rejected"] is True


@pytest.mark.asyncio
async def test_transaction_rollback_restores_initial_state(db) -> None:
    plan = await LegacyOwnerCutoverService.plan(db)
    await LegacyOwnerCutoverService.execute(
        db,
        plan_token=plan["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    assert await db.scalar(select(StaffUser.id)) is not None
    await db.rollback()

    assert await db.scalar(select(StaffUser.id)) is None
    assert await db.scalar(select(TenantAuditEvent.id)) is None
    state = await _state(db)
    assert state.mode == "legacy"
    assert state.owner_staff_user_id is None
    assert state.legacy_token_version == 1


@pytest.mark.asyncio
async def test_rollback_after_self_service_change_keeps_owner_and_invalidates_staff_jwt(db) -> None:
    cutover_plan = await LegacyOwnerCutoverService.plan(db)
    result = await LegacyOwnerCutoverService.execute(
        db,
        plan_token=cutover_plan["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    user = await db.get(StaffUser, result["staff_user_id"])
    user.password_hash = CredentialService.hash_password("self-service-password-2026")
    user.password_changed_at = datetime.now(timezone.utc)
    user.auth_version += 1
    self_service_auth_version = user.auth_version
    db.add(user)
    await db.flush()

    rollback_plan = await LegacyOwnerCutoverService.plan(db, for_action="rollback")
    assert rollback_plan["ready"] is True
    assert rollback_plan["changes"] == ["restore_legacy_auth"]
    rollback_result = await LegacyOwnerCutoverService.rollback(
        db, plan_token=rollback_plan["plan_token"]
    )

    await db.refresh(user)
    state = await _state(db)
    assert rollback_result["auth_mode"] == "legacy"
    assert rollback_result["legacy_token_version"] == 3
    assert state.owner_staff_user_id == user.id
    assert user.auth_version == self_service_auth_version + 1
    assert CredentialService.verify_password("self-service-password-2026", user.password_hash)
    assert not CredentialService.verify_password(settings.ADMIN_PASSWORD, user.password_hash)
    verification = await LegacyOwnerCutoverService.verify(db)
    assert verification["ready"] is True
    assert verification["credential_matches"] is True
    assert len(verification["runtime_binding"]) == 64
    assert verification["can_change_password"] is False
    assert verification["auth_source_staff_password"] is False
    assert verification["legacy_jwt_rejected"] is False
    assert verification["legacy_google_auth_rejected"] is False

    repeated_plan = await LegacyOwnerCutoverService.plan(db, for_action="rollback")
    repeated = await LegacyOwnerCutoverService.rollback(
        db, plan_token=repeated_plan["plan_token"]
    )
    assert repeated_plan["changes"] == []
    assert repeated["changed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("telegram_id", "telegram_username"),
    [(123456789, None), (None, "system_owner")],
)
async def test_blocks_telegram_shared_identity(db, telegram_id, telegram_username) -> None:
    await _seed_bound_owner(
        db,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
    )
    plan = await LegacyOwnerCutoverService.plan(db)
    assert plan["ready"] is False
    assert "existing_staff_identity_not_exact" in plan["blockers"]


@pytest.mark.asyncio
async def test_blocks_noncanonical_runtime_identity_without_exposing_it(db, monkeypatch) -> None:
    configured = f" {settings.ADMIN_USERNAME.upper()} "
    monkeypatch.setattr(settings, "ADMIN_USERNAME", configured)
    plan = await LegacyOwnerCutoverService.plan(db)
    assert plan["ready"] is False
    assert "runtime_identity_not_canonical" in plan["blockers"]
    assert configured not in json.dumps(plan)


@pytest.mark.asyncio
async def test_blocks_casefold_collision_and_shared_tenant_identity(db) -> None:
    first = StaffUser(
        display_name="First",
        username=settings.ADMIN_USERNAME,
        status="active",
        primary_role="owner",
        roles=["owner"],
    )
    second = StaffUser(
        display_name="Second",
        username=settings.ADMIN_USERNAME.upper(),
        status="active",
        primary_role="owner",
        roles=["owner"],
    )
    db.add_all([first, second])
    await db.flush()
    collision_plan = await LegacyOwnerCutoverService.plan(db)
    assert collision_plan["ready"] is False
    assert "staff_identity_collision" in collision_plan["blockers"]

    await db.delete(second)
    await db.delete(first)
    await db.flush()
    owner = await _seed_bound_owner(db)
    tenant_b = Tenant(
        slug="shared-b",
        display_name="Shared B",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(tenant_b)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    shared_plan = await LegacyOwnerCutoverService.plan(db)
    assert shared_plan["ready"] is False
    assert "shared_or_incomplete_tenant_identity" in shared_plan["blockers"]


@pytest.mark.asyncio
async def test_stale_plan_does_not_mutate_and_one_time_credential_rotates_retained_owner(
    db, monkeypatch
) -> None:
    plan = await LegacyOwnerCutoverService.plan(db)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "rotated-runtime-password-2026")
    with pytest.raises(LegacyOwnerCutoverBlockedError, match="stale"):
        await LegacyOwnerCutoverService.execute(
            db,
            plan_token=plan["plan_token"],
            new_password=CUTOVER_PASSWORD,
        )
    assert await db.scalar(select(StaffUser.id)) is None
    state = await _state(db)
    assert (state.mode, state.legacy_token_version, state.owner_staff_user_id) == (
        "legacy", 1, None
    )

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-only-password")
    owner = await _seed_bound_owner(db)
    owner.password_hash = CredentialService.hash_password("different-password-2026")
    db.add(owner)
    await db.flush()
    reviewed = await LegacyOwnerCutoverService.plan(db)
    assert reviewed["ready"] is True
    result = await LegacyOwnerCutoverService.execute(
        db,
        plan_token=reviewed["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    await db.refresh(owner)
    assert result["auth_mode"] == "staff_shadow"
    assert CredentialService.verify_password(CUTOVER_PASSWORD, owner.password_hash)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_password", ["short", "я" * 37])
async def test_invalid_one_time_credential_is_rejected_without_mutation(
    db, invalid_password
) -> None:
    plan = await LegacyOwnerCutoverService.plan(db)
    with pytest.raises(LegacyOwnerCutoverBlockedError, match="password policy"):
        await LegacyOwnerCutoverService.execute(
            db,
            plan_token=plan["plan_token"],
            new_password=invalid_password,
        )
    assert await db.scalar(select(StaffUser.id)) is None
    state = await _state(db)
    assert (state.mode, state.owner_staff_user_id, state.legacy_token_version) == (
        "legacy",
        None,
        1,
    )


@pytest.mark.asyncio
async def test_short_retained_runtime_credential_does_not_block_long_db_credential(
    db, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "legacy")
    plan = await LegacyOwnerCutoverService.plan(db)
    assert plan["ready"] is True
    assert plan["blockers"] == []
    result = await LegacyOwnerCutoverService.execute(
        db,
        plan_token=plan["plan_token"],
        new_password=CUTOVER_PASSWORD,
    )
    user = await db.get(StaffUser, result["staff_user_id"])
    assert CredentialService.verify_password(CUTOVER_PASSWORD, user.password_hash)
    assert not CredentialService.verify_password("legacy", user.password_hash)


@pytest.mark.asyncio
async def test_advisory_lock_serializes_cutover(db_engine) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as planner:
        plan = await LegacyOwnerCutoverService.plan(planner)
        await planner.rollback()
    async with factory() as holder, factory() as contender:
        assert await holder.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": LegacyOwnerCutoverService.LOCK_KEY},
        )
        with pytest.raises(LegacyOwnerCutoverBlockedError, match="owns the lock"):
            await LegacyOwnerCutoverService.execute(
                contender,
                plan_token=plan["plan_token"],
                new_password=CUTOVER_PASSWORD,
            )
        await contender.rollback()
        await holder.rollback()


@pytest.mark.asyncio
async def test_state_service_locks_and_reads_seeded_singleton(db) -> None:
    state = await LegacyOwnerAuthStateService.get(db, for_update=True)
    assert state.id == 1
    assert state.mode == LegacyOwnerAuthStateService.MODE_LEGACY
    assert state.legacy_token_version == 1
