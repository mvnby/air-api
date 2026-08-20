from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from core.database import get_session
from models import LegacyOwnerAuthState, StaffUser, TenantMembership
from models.tenancy import TenantScope
from schemas import ManagerStaffUpdatePayload
from services.bot_access_service import BotAccessService
from services.credential_service import CredentialService
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_cutover_service import (
    LegacyOwnerCutoverBlockedError,
    LegacyOwnerCutoverService,
)
from services.legacy_owner_managed_identity_service import (
    LegacyOwnerManagedIdentityError,
)
from services.manager_account_credential_service import (
    ManagerAccountCredentialError,
    ManagerAccountCredentialService,
)
from services.staff_user_service import StaffUserService


async def _client_with_independent_sessions(db_engine):
    from main import app

    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return app, AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def _bound_owner(
    db,
    *,
    mode: str,
    telegram_id: int | None = None,
) -> StaffUser:
    owner = StaffUser(
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
        telegram_username="bound_owner" if telegram_id else None,
    )
    db.add(owner)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode = mode
    state.owner_staff_user_id = int(owner.id)
    state.legacy_token_version = 2 if mode != "legacy" else 3
    db.add(state)
    await db.commit()
    return owner


@pytest.mark.asyncio
async def test_generic_staff_mutation_rejects_bound_owner_with_explicit_api_code(
    async_client,
    db,
) -> None:
    owner = await _bound_owner(db, mode="legacy")
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    response = await async_client.patch(
        f"/api/manager/staff/{owner.id}",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={
            "username": "renamed-owner",
            "status": "blocked",
            "primary_role": "manager",
            "password": "generic-reset-password-2026",
            "telegram_id": 777001,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "legacy_owner_managed"
    await db.refresh(owner)
    assert owner.username == settings.ADMIN_USERNAME
    assert owner.status == "active"
    assert owner.primary_role == "owner"
    assert owner.telegram_id is None
    assert CredentialService.verify_password(settings.ADMIN_PASSWORD, owner.password_hash)


@pytest.mark.asyncio
async def test_self_service_is_mode_gated_and_shadow_change_remains_rollback_compatible(db) -> None:
    owner = await _bound_owner(db, mode="legacy")
    owner_id = int(owner.id)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    with pytest.raises(ManagerAccountCredentialError) as blocked:
        await ManagerAccountCredentialService.change_password(
            db,
            staff_user_id=owner_id,
            actor_username=str(owner.username),
            tenant_scope=scope,
            current_password=settings.ADMIN_PASSWORD,
            new_password="new-owner-password-2026",
        )
    assert blocked.value.code == "self_service_unavailable"
    await db.rollback()

    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode = "staff_shadow"
    db.add(state)
    await db.commit()
    owner = await db.get(StaffUser, owner_id)
    await ManagerAccountCredentialService.change_password(
        db,
        staff_user_id=owner_id,
        actor_username=str(owner.username),
        tenant_scope=scope,
        current_password=settings.ADMIN_PASSWORD,
        new_password="new-owner-password-2026",
    )
    await db.refresh(owner)
    assert CredentialService.verify_password("new-owner-password-2026", owner.password_hash)

    rollback_plan = await LegacyOwnerCutoverService.plan(db, for_action="rollback")
    assert rollback_plan["ready"] is True
    rollback = await LegacyOwnerCutoverService.rollback(
        db,
        plan_token=rollback_plan["plan_token"],
    )
    assert rollback["auth_mode"] == "legacy"
    assert CredentialService.verify_password("new-owner-password-2026", owner.password_hash)


@pytest.mark.asyncio
async def test_rejected_telegram_login_does_not_mutate_bound_owner(
    async_client,
    db,
    monkeypatch,
) -> None:
    owner = await _bound_owner(db, mode="legacy", telegram_id=777002)
    original_username = owner.telegram_username
    original_last_login = owner.last_login_at
    monkeypatch.setattr(
        StaffUserService,
        "verify_telegram_login_payload",
        classmethod(lambda cls, payload, max_age=None: True),
    )
    response = await async_client.post(
        "/login/telegram",
        json={
            "id": 777002,
            "username": "mutated_by_login",
            "auth_date": 1,
            "hash": "signed",
        },
    )
    assert response.status_code == 401
    await db.refresh(owner)
    assert owner.telegram_username == original_username
    assert owner.last_login_at == original_last_login

    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode = "staff_shadow"
    owner.primary_role = "manager"
    owner.roles = ["manager"]
    db.add_all([state, owner])
    await db.commit()
    corrupted_response = await async_client.post(
        "/login/telegram",
        json={
            "id": 777002,
            "username": "still_must_not_mutate",
            "auth_date": 1,
            "hash": "signed",
        },
    )
    assert corrupted_response.status_code == 401
    await db.refresh(owner)
    assert owner.telegram_username == original_username
    assert owner.last_login_at == original_last_login


@pytest.mark.asyncio
async def test_bot_access_is_state_and_exact_identity_gated(db) -> None:
    owner = await _bound_owner(db, mode="legacy", telegram_id=777003)
    legacy = await BotAccessService.get_context(db, 777003)
    assert legacy.is_staff is False

    state = await db.get(LegacyOwnerAuthState, 1)
    state.mode = "staff_shadow"
    db.add(state)
    await db.commit()
    shadow = await BotAccessService.get_context(db, 777003)
    assert shadow.is_staff is True
    assert shadow.primary_role == "owner"

    owner.roles = ["manager"]
    owner.primary_role = "manager"
    db.add(owner)
    await db.commit()
    corrupted = await BotAccessService.get_context(db, 777003)
    assert corrupted.is_staff is False


@pytest.mark.asyncio
async def test_cutover_waits_for_login_state_lock(db_engine) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as planner:
        plan = await LegacyOwnerCutoverService.plan(planner)
        await planner.rollback()

    async with factory() as login_session:
        await LegacyOwnerAuthStateService.get(login_session, for_update=True)

        async def execute_cutover():
            async with factory() as operation_session:
                result = await LegacyOwnerCutoverService.execute(
                    operation_session,
                    plan_token=plan["plan_token"],
                )
                await operation_session.commit()
                return result

        task = asyncio.create_task(execute_cutover())
        await asyncio.sleep(0.05)
        assert task.done() is False
        await login_session.rollback()
        result = await task
    assert result["auth_mode"] == "staff_shadow"


@pytest.mark.asyncio
async def test_real_legacy_login_race_with_cutover_issues_only_stale_token(
    db_engine,
    monkeypatch,
) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as planner:
        plan = await LegacyOwnerCutoverService.plan(planner)
        await planner.rollback()

    state_locked = asyncio.Event()
    release_login = asyncio.Event()
    original_state = LegacyOwnerAuthGuard.state.__func__

    async def gated_state(cls, session, *, for_update=False):
        state = await original_state(cls, session, for_update=for_update)
        if for_update:
            state_locked.set()
            await release_login.wait()
        return state

    monkeypatch.setattr(
        LegacyOwnerAuthGuard,
        "state",
        classmethod(gated_state),
    )
    app, client = await _client_with_independent_sessions(db_engine)
    try:
        async with client:
            login_task = asyncio.create_task(
                client.post(
                    "/login/access-token",
                    data={
                        "username": settings.ADMIN_USERNAME,
                        "password": settings.ADMIN_PASSWORD,
                    },
                )
            )
            await asyncio.wait_for(state_locked.wait(), timeout=3)

            async def execute_cutover():
                async with factory() as session:
                    result = await LegacyOwnerCutoverService.execute(
                        session,
                        plan_token=plan["plan_token"],
                    )
                    await session.commit()
                    return result

            cutover_task = asyncio.create_task(execute_cutover())
            await asyncio.sleep(0.05)
            assert cutover_task.done() is False
            release_login.set()
            login = await login_task
            cutover = await cutover_task
            assert login.status_code == 200
            assert cutover["auth_mode"] == "staff_shadow"
            stale = await client.get(
                "/api/manager/me",
                headers={
                    "Authorization": f"Bearer {login.json()['access_token']}"
                },
            )
            assert stale.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_rollback_waits_for_staff_login_state_lock(db_engine) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        cutover_plan = await LegacyOwnerCutoverService.plan(seed)
        await LegacyOwnerCutoverService.execute(seed, plan_token=cutover_plan["plan_token"])
        await seed.commit()
    async with factory() as planner:
        rollback_plan = await LegacyOwnerCutoverService.plan(
            planner, for_action="rollback"
        )
        await planner.rollback()

    async with factory() as login_session:
        await LegacyOwnerAuthStateService.get(login_session, for_update=True)

        async def execute_rollback():
            async with factory() as operation_session:
                result = await LegacyOwnerCutoverService.rollback(
                    operation_session,
                    plan_token=rollback_plan["plan_token"],
                )
                await operation_session.commit()
                return result

        task = asyncio.create_task(execute_rollback())
        await asyncio.sleep(0.05)
        assert task.done() is False
        await login_session.rollback()
        result = await task
    assert result["auth_mode"] == "legacy"


@pytest.mark.asyncio
async def test_real_staff_login_race_with_rollback_cannot_survive_rollback(
    db_engine,
    monkeypatch,
) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        cutover_plan = await LegacyOwnerCutoverService.plan(seed)
        await LegacyOwnerCutoverService.execute(
            seed,
            plan_token=cutover_plan["plan_token"],
        )
        await seed.commit()
    async with factory() as planner:
        rollback_plan = await LegacyOwnerCutoverService.plan(
            planner,
            for_action="rollback",
        )
        await planner.rollback()

    state_locked = asyncio.Event()
    release_login = asyncio.Event()
    original_state = LegacyOwnerAuthGuard.state.__func__

    async def gated_state(cls, session, *, for_update=False):
        state = await original_state(cls, session, for_update=for_update)
        if for_update:
            state_locked.set()
            await release_login.wait()
        return state

    monkeypatch.setattr(
        LegacyOwnerAuthGuard,
        "state",
        classmethod(gated_state),
    )
    app, client = await _client_with_independent_sessions(db_engine)
    try:
        async with client:
            login_task = asyncio.create_task(
                client.post(
                    "/login/access-token",
                    data={
                        "username": settings.ADMIN_USERNAME,
                        "password": settings.ADMIN_PASSWORD,
                    },
                )
            )
            await asyncio.wait_for(state_locked.wait(), timeout=3)

            async def execute_rollback():
                async with factory() as session:
                    result = await LegacyOwnerCutoverService.rollback(
                        session,
                        plan_token=rollback_plan["plan_token"],
                    )
                    await session.commit()
                    return result

            rollback_task = asyncio.create_task(execute_rollback())
            await asyncio.sleep(0.05)
            assert rollback_task.done() is False
            release_login.set()
            login = await login_task
            rollback = await rollback_task
            assert rollback["auth_mode"] == "legacy"
            assert login.status_code in {200, 400}
            if login.status_code == 200:
                stale = await client.get(
                    "/api/manager/me",
                    headers={
                        "Authorization": f"Bearer {login.json()['access_token']}"
                    },
                )
                assert stale.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_self_service_race_stales_rollback_then_fresh_rollback_preserves_change(
    db_engine,
) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        cutover_plan = await LegacyOwnerCutoverService.plan(seed)
        cutover = await LegacyOwnerCutoverService.execute(
            seed, plan_token=cutover_plan["plan_token"]
        )
        await seed.commit()
        owner_id = int(cutover["staff_user_id"])
    async with factory() as planner:
        stale_rollback_plan = await LegacyOwnerCutoverService.plan(
            planner, for_action="rollback"
        )
        await planner.rollback()

    async with factory() as self_service_session:
        await LegacyOwnerAuthStateService.get(self_service_session, for_update=True)

        async def attempt_stale_rollback():
            async with factory() as rollback_session:
                try:
                    await LegacyOwnerCutoverService.rollback(
                        rollback_session,
                        plan_token=stale_rollback_plan["plan_token"],
                    )
                except Exception:
                    await rollback_session.rollback()
                    raise

        rollback_task = asyncio.create_task(attempt_stale_rollback())
        await asyncio.sleep(0.05)
        assert rollback_task.done() is False
        await ManagerAccountCredentialService.change_password(
            self_service_session,
            staff_user_id=owner_id,
            actor_username=settings.ADMIN_USERNAME,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            current_password=settings.ADMIN_PASSWORD,
            new_password="raced-self-service-password-2026",
        )
        with pytest.raises(LegacyOwnerCutoverBlockedError, match="stale"):
            await rollback_task

    async with factory() as retry:
        fresh = await LegacyOwnerCutoverService.plan(retry, for_action="rollback")
        rolled_back = await LegacyOwnerCutoverService.rollback(
            retry, plan_token=fresh["plan_token"]
        )
        await retry.commit()
        owner = await retry.get(StaffUser, owner_id)
        assert rolled_back["auth_mode"] == "legacy"
        assert CredentialService.verify_password(
            "raced-self-service-password-2026", owner.password_hash
        )
