import json
import asyncio
from datetime import timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from core.security import ALGORITHM, create_access_token
from models import StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.tenancy import TenantScope
from services.credential_service import CredentialService
from services.manager_account_credential_service import ManagerAccountCredentialService
from services.staff_user_service import StaffUserService


CURRENT_PASSWORD = "current-password-2026"
NEW_PASSWORD = "replacement-password-2026"


async def _create_staff(
    db,
    *,
    tenant_id: int,
    username: str,
    role: str,
    password: str = CURRENT_PASSWORD,
    must_change_password: bool = True,
) -> StaffUser:
    user = StaffUser(
        display_name=username,
        status="active",
        primary_role=role,
        roles=[role],
        username=username,
        password_hash=CredentialService.hash_password(password),
        must_change_password=must_change_password,
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=int(user.id),
            role=role,
            status="active",
        )
    )
    await db.commit()
    return user


async def _create_tenant_b(db) -> tuple[Tenant, Storefront]:
    tenant = Tenant(
        id=2,
        slug="tenant-b",
        display_name="Tenant B",
        status="active",
        is_system=False,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        id=2,
        tenant_id=2,
        slug="main",
        display_name="Tenant B Main",
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    return tenant, storefront


def _token(user: StaffUser, *, auth_source: str) -> str:
    return create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "auth_source": auth_source,
        },
        expires_delta=timedelta(minutes=10),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "manager"])
async def test_staff_changes_only_own_password_and_revokes_all_prior_tokens(
    async_client: AsyncClient,
    db,
    caplog,
    role: str,
) -> None:
    await _create_tenant_b(db)
    actor = await _create_staff(
        db,
        tenant_id=1,
        username=f"{role}-a",
        role=role,
    )
    tenant_b_user = await _create_staff(
        db,
        tenant_id=2,
        username=f"{role}-b",
        role=role,
        password="tenant-b-password-2026",
        must_change_password=False,
    )
    actor_original_hash = str(actor.password_hash)
    tenant_b_original_hash = str(tenant_b_user.password_hash)
    tenant_b_original_version = int(tenant_b_user.auth_version)
    password_token = _token(actor, auth_source="staff_password")
    telegram_token = _token(actor, auth_source="telegram")

    me_before = await async_client.get(
        "/api/manager/me",
        headers={"Authorization": f"Bearer {password_token}"},
    )
    assert me_before.status_code == 200
    assert me_before.json()["can_change_password"] is True
    assert me_before.json()["must_change_password"] is True
    assert "password_hash" not in me_before.text

    changed = await async_client.post(
        "/api/manager/account/change-password",
        headers={
            "Authorization": f"Bearer {password_token}",
            "X-Request-ID": "credential-change-request-2026",
        },
        json={
            "current_password": CURRENT_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )

    assert changed.status_code == 204
    assert changed.content == b""
    assert 'access_token=""' in changed.headers["set-cookie"]
    assert "Max-Age=0" in changed.headers["set-cookie"]

    await db.refresh(actor)
    await db.refresh(tenant_b_user)
    assert actor.password_hash != actor_original_hash
    assert CredentialService.verify_password(NEW_PASSWORD, actor.password_hash)
    assert actor.password_changed_at is not None
    assert actor.auth_version == 2
    assert actor.must_change_password is False
    assert tenant_b_user.password_hash == tenant_b_original_hash
    assert tenant_b_user.auth_version == tenant_b_original_version

    for old_token in (password_token, telegram_token):
        revoked = await async_client.get(
            "/api/manager/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert revoked.status_code == 401

    old_login = await async_client.post(
        "/login/access-token",
        data={"username": actor.username, "password": CURRENT_PASSWORD},
    )
    assert old_login.status_code == 400
    new_login = await async_client.post(
        "/login/access-token",
        data={"username": actor.username, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200
    new_claims = jwt.decode(
        new_login.json()["access_token"],
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    assert new_claims["auth_version"] == 2
    assert CURRENT_PASSWORD not in new_login.text
    assert NEW_PASSWORD not in new_login.text
    assert actor.password_hash not in new_login.text

    audits = list(
        (
            await db.execute(
                select(TenantAuditEvent).where(
                    TenantAuditEvent.action == "staff_credential.changed"
                )
            )
        ).scalars()
    )
    assert len(audits) == 1
    audit = audits[0]
    assert audit.tenant_id == 1
    assert audit.storefront_id == 1
    assert audit.actor_staff_user_id == actor.id
    assert audit.entity_id == actor.id
    assert audit.request_id == "credential-change-request-2026"
    assert audit.change_set == {
        "auth_version": {"before": 1, "after": 2},
        "required_change_cleared": True,
    }
    secret_evidence = json.dumps(audit.change_set) + caplog.text
    assert CURRENT_PASSWORD not in secret_evidence
    assert NEW_PASSWORD not in secret_evidence
    assert actor.password_hash not in secret_evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current_password", "new_password", "error_code"),
    [
        ("wrong-current-password", NEW_PASSWORD, "invalid_current_password"),
        (CURRENT_PASSWORD, CURRENT_PASSWORD, "password_reuse"),
        (CURRENT_PASSWORD, "too-short", "password_too_short"),
        (CURRENT_PASSWORD, "я" * 37, "password_too_long"),
        (CURRENT_PASSWORD, "\ud800" * 12, "password_invalid_encoding"),
    ],
)
async def test_rejected_password_change_does_not_mutate_identity_or_audit(
    async_client: AsyncClient,
    db,
    current_password: str,
    new_password: str,
    error_code: str,
) -> None:
    actor = await _create_staff(
        db,
        tenant_id=1,
        username=f"reject-{error_code}",
        role="manager",
    )
    original_hash = str(actor.password_hash)
    token = _token(actor, auth_source="staff_password")

    response = await async_client.post(
        "/api/manager/account/change-password",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        content=json.dumps(
            {
                "current_password": current_password,
                "new_password": new_password,
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == error_code
    assert "set-cookie" not in response.headers
    await db.refresh(actor)
    assert actor.password_hash == original_hash
    assert actor.auth_version == 1
    assert actor.password_changed_at is None
    assert actor.must_change_password is True
    assert (
        await db.scalar(
            select(TenantAuditEvent).where(
                TenantAuditEvent.action == "staff_credential.changed"
            )
        )
    ) is None


@pytest.mark.asyncio
async def test_legacy_env_login_reports_self_service_unavailable(
    async_client: AsyncClient,
) -> None:
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    response = await async_client.post(
        "/api/manager/account/change-password",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={
            "current_password": settings.ADMIN_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_service_unavailable"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_staff_token_without_credential_version_is_rejected(
    async_client: AsyncClient,
    db,
) -> None:
    actor = await _create_staff(
        db,
        tenant_id=1,
        username="unversioned-token",
        role="manager",
    )
    token = create_access_token(
        {"sub": actor.username, "staff_user_id": actor.id, "auth_source": "old"},
        expires_delta=timedelta(minutes=10),
    )

    response = await async_client.get(
        "/api/manager/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_passwordless_staff_reports_self_service_unavailable(
    async_client: AsyncClient,
    db,
) -> None:
    actor = StaffUser(
        display_name="Telegram-only manager",
        status="active",
        primary_role="manager",
        roles=["manager"],
        username="telegram-only-manager",
        password_hash=None,
    )
    db.add(actor)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(actor.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()
    token = _token(actor, auth_source="telegram")

    me = await async_client.get(
        "/api/manager/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["can_change_password"] is False

    response = await async_client.post(
        "/api/manager/account/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": CURRENT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_service_unavailable"


@pytest.mark.asyncio
async def test_login_race_cannot_issue_new_version_token_for_old_password(db_engine) -> None:
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as seed_session:
        actor = await _create_staff(
            seed_session,
            tenant_id=1,
            username="login-race-manager",
            role="manager",
        )
        actor_id = int(actor.id)

    commit_reached = asyncio.Event()
    allow_login_commit = asyncio.Event()
    async with session_factory() as login_session:
        original_commit = login_session.commit

        async def paused_commit() -> None:
            commit_reached.set()
            await allow_login_commit.wait()
            await original_commit()

        login_session.commit = paused_commit  # type: ignore[method-assign]
        login_task = asyncio.create_task(
            StaffUserService.authenticate_password(
                login_session,
                "login-race-manager",
                CURRENT_PASSWORD,
            )
        )
        await commit_reached.wait()

        async with session_factory() as change_session:
            await ManagerAccountCredentialService.change_password(
                change_session,
                staff_user_id=actor_id,
                actor_username="login-race-manager",
                tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
                current_password=CURRENT_PASSWORD,
                new_password=NEW_PASSWORD,
            )

        allow_login_commit.set()
        authentication = await login_task

    assert authentication is not None
    assert authentication.auth_version == 1
    async with session_factory() as verification_session:
        persisted = await verification_session.get(StaffUser, actor_id)
        assert persisted is not None
        assert persisted.auth_version == 2
        assert CredentialService.verify_password(NEW_PASSWORD, persisted.password_hash)

    token = create_access_token(
        {
            "sub": authentication.user.username,
            "staff_user_id": actor_id,
            "auth_version": authentication.auth_version,
            "auth_source": "staff_password",
        },
        expires_delta=timedelta(minutes=10),
    )
    claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["auth_version"] == 1
