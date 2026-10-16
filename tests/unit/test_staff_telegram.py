from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from core.security import AuthenticatedUser
from models import Installer, LegacyOwnerAuthState, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.staff_telegram import StaffTelegramChallenge
from services.credential_service import CredentialService
from services.staff_user_service import StaffUserService
from services.staff_telegram_service import StaffTelegramService as Telegram
from services.staff_telegram_security import StaffTelegramError, digest
from services.staff_telegram_widget import consume_widget_proof
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from core.database import get_session
from core.security import get_current_auth_context
from core.config import settings
from routers.manager_account_telegram import router as link_router
from routers.auth_telegram import router as login_router
from routers.internal_bot_account_links import router as bot_router


@pytest.fixture
async def telegram_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "kitlane_test_bot")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
                         Storefront(id=1, tenant_id=1, slug="main", display_name="MVN", status="active", is_default=True),
                         LegacyOwnerAuthState()])
        user = StaffUser(display_name="Manager", username="tg-manager", primary_role="manager", roles=["manager"],
                         password_hash=CredentialService.hash_password("test-password-123"))
        session.add(user)
        await session.flush()
        session.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager"))
        await session.commit()
        auth = AuthenticatedUser(username=user.username, auth_source="staff_password", staff_user_id=user.id,
                                 role="manager", tenant_id=1, storefront_id=1, tenant_membership_id=1,
                                 auth_version=user.auth_version, is_system_tenant=True)
        yield session, user, auth
    await engine.dispose()


def token(result):
    return result["deep_link"].split("?start=", 1)[1].split("_", 1)[1]


async def claim(session, result, *, telegram_id=101, purpose="link"):
    return await Telegram.claim(session, token=token(result), telegram_id=telegram_id,
                                telegram_username="real_user", telegram_display_name="Real Telegram",
                                chat_id=telegram_id, message_id=10, purpose=purpose)


@pytest.mark.asyncio
async def test_link_requires_both_browser_and_bot_proof_rotates_credentials_and_audits(telegram_db):
    session, user, auth = telegram_db
    result, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
    row = await session.get(StaffTelegramChallenge, result["challenge_id"])
    assert row.token_hash == digest(token(result))
    assert token(result) not in str(row.model_dump())
    assert len("link_" + token(result)) < 64
    with pytest.raises(StaffTelegramError):
        await Telegram.confirm(session, challenge_id=row.id, browser_secret=secret, auth=auth, telegram_id=101)
    await claim(session, result)
    with pytest.raises(StaffTelegramError) as exc:
        await Telegram.status(session, challenge_id=row.id, browser_secret="other-browser", purpose="link", auth=auth)
    assert exc.value.status_code == 404
    with pytest.raises(StaffTelegramError):
        await Telegram.confirm(session, challenge_id=row.id, browser_secret=secret, auth=auth, telegram_id=202)
    linked = await Telegram.confirm(session, challenge_id=row.id, browser_secret=secret, auth=auth, telegram_id=101)
    assert linked.telegram_id == 101
    assert linked.telegram_verified_at is not None
    assert linked.auth_version == 2
    assert (await session.scalar(select(TenantAuditEvent))).action == "staff.telegram_linked"
    status = await Telegram.status(session, challenge_id=row.id, browser_secret=secret, purpose="link",
                                  auth=replace(auth, auth_version=linked.auth_version))
    assert status["status"] == "confirmed"


@pytest.mark.asyncio
async def test_claim_is_same_actor_idempotent_but_not_transferable(telegram_db):
    session, _, auth = telegram_db
    result, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
    first = await claim(session, result)
    assert await claim(session, result) == first
    with pytest.raises(StaffTelegramError) as exc:
        await claim(session, result, telegram_id=202)
    assert exc.value.code == "telegram_challenge_claimed"


@pytest.mark.asyncio
async def test_expiry_and_new_link_invalidate_old_proof(telegram_db):
    session, _, auth = telegram_db
    old, _ = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
    current, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
    with pytest.raises(StaffTelegramError):
        await claim(session, old)
    row = await session.get(StaffTelegramChallenge, current["challenge_id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.commit()
    with pytest.raises(StaffTelegramError) as exc:
        await claim(session, current)
    assert exc.value.code == "telegram_challenge_expired"


@pytest.mark.asyncio
async def test_link_never_steals_another_account(telegram_db):
    session, user, auth = telegram_db
    other = StaffUser(display_name="Other", telegram_id=101)
    session.add(other)
    await session.commit()
    result, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
    await claim(session, result)
    with pytest.raises(StaffTelegramError) as exc:
        await Telegram.confirm(session, challenge_id=result["challenge_id"], browser_secret=secret, auth=auth, telegram_id=101)
    assert exc.value.code == "telegram_already_linked"
    assert user.telegram_id is None
    assert other.telegram_id == 101


@pytest.mark.asyncio
async def test_bot_login_requires_explicit_matching_actor_approval_and_single_use_browser(telegram_db):
    session, user, _ = telegram_db
    user.telegram_id = 101
    await session.commit()
    result, secret = await Telegram.start(session, purpose="login", browser_secret=None)
    assert len(result["browser_code"]) == 8
    claimed = await claim(session, result, purpose="login")
    assert claimed["status"] == "approval_pending"
    with pytest.raises(StaffTelegramError):
        await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)
    with pytest.raises(StaffTelegramError):
        await Telegram.decide(session, challenge_id=result["challenge_id"], telegram_id=202, approve=True)
    await Telegram.decide(session, challenge_id=result["challenge_id"], telegram_id=101, approve=True)
    with pytest.raises(StaffTelegramError):
        await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret="different")
    logged_in = await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)
    assert logged_in.id == user.id
    assert logged_in.telegram_verified_at is not None
    with pytest.raises(StaffTelegramError):
        await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "disabled", "alias", "membership"])
async def test_login_rechecks_identity_after_approval(telegram_db, change):
    session, user, _ = telegram_db
    user.telegram_id = 101
    await session.commit()
    result, secret = await Telegram.start(session, purpose="login", browser_secret=None)
    await claim(session, result, purpose="login")
    await Telegram.decide(session, challenge_id=result["challenge_id"], telegram_id=101, approve=True)
    if change == "version":
        user.auth_version += 1
    elif change == "disabled":
        user.status = "inactive"
    elif change == "alias":
        user.merged_into_staff_user_id = 999
    else:
        membership = await session.scalar(select(TenantMembership))
        membership.status = "disabled"
    await session.commit()
    with pytest.raises((StaffTelegramError, RuntimeError)):
        await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)


@pytest.mark.asyncio
async def test_unknown_telegram_cannot_create_or_login_account(telegram_db):
    session, _, _ = telegram_db
    result, _ = await Telegram.start(session, purpose="login", browser_secret=None)
    with pytest.raises(StaffTelegramError) as exc:
        await claim(session, result, purpose="login")
    assert exc.value.status_code == 403
    assert len(list((await session.execute(select(StaffUser))).scalars())) == 1


@pytest.mark.asyncio
async def test_disconnect_checks_other_factor_and_clears_installer_mirror(telegram_db):
    session, user, auth = telegram_db
    installer = Installer(name="Manager", telegram_id=101)
    session.add(installer)
    await session.flush()
    user.telegram_id, user.legacy_installer_id = 101, installer.id
    await session.commit()
    with pytest.raises(StaffTelegramError):
        await Telegram.disconnect(session, auth=auth, current_password="wrong")
    await Telegram.disconnect(session, auth=auth, current_password="test-password-123")
    assert user.telegram_id is None
    assert installer.telegram_id is None
    assert user.auth_version == 2


@pytest.mark.asyncio
async def test_legacy_widget_proof_cannot_be_replayed(telegram_db):
    session, _, _ = telegram_db
    await consume_widget_proof(session, {"hash": "signed-telegram-proof"})
    with pytest.raises(StaffTelegramError) as exc:
        await consume_widget_proof(session, {"hash": "signed-telegram-proof"})
    assert exc.value.code == "telegram_proof_used"


@pytest.mark.asyncio
async def test_widget_freezes_auth_version_before_commit_even_if_disconnect_finishes_immediately(telegram_db, monkeypatch):
    from unittest.mock import AsyncMock
    import jwt
    from routers.auth import router as auth_router
    session, user, auth = telegram_db
    user.telegram_id = 101
    await session.commit()
    staff_id = user.id
    original_commit = session.commit
    monkeypatch.setattr(StaffUserService, "verify_telegram_login_payload", classmethod(lambda cls, payload: True))
    async def commit_then_disconnect():
        await original_commit()
        async with AsyncSession(session.bind, expire_on_commit=False) as concurrent:
            await Telegram.disconnect(concurrent, auth=auth, current_password="test-password-123")
    monkeypatch.setattr(session, "commit", commit_then_disconnect)
    monkeypatch.setattr(session, "refresh", AsyncMock(side_effect=AssertionError("post-commit refresh can upgrade stale Telegram proof")))
    app = FastAPI()
    app.include_router(auth_router)
    async def db_session():
        yield session
    app.dependency_overrides[get_session] = db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/login/telegram", json={"id": 101, "auth_date": 1, "hash": "fresh-signed-proof"})
    assert response.status_code == 200
    payload = jwt.decode(response.json()["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["auth_version"] == 1
    async with AsyncSession(session.bind) as concurrent:
        current = await concurrent.get(StaffUser, staff_id)
        assert current.auth_version == 2
        assert current.telegram_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["disconnect", "replace", "generic_unlink"])
async def test_retired_telegram_never_becomes_a_legacy_owner_or_notification_target(telegram_db, monkeypatch, mutation):
    from services.bot_access_service import BotAccessService
    from services.staff_telegram_notifications import legacy_recipient_ids
    from services.communications.recipient_directory import ManagementRecipientDirectory
    from services.staff_user_service import StaffUserService
    from schemas import ManagerStaffUpdatePayload
    session, user, auth = telegram_db
    monkeypatch.setattr(settings, "ADMIN_IDS", "101", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    user.telegram_id = 101
    await session.commit()
    if mutation == "disconnect":
        await Telegram.disconnect(session, auth=auth, current_password="test-password-123")
    elif mutation == "replace":
        result, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
        await claim(session, result, telegram_id=202)
        await Telegram.confirm(session, challenge_id=result["challenge_id"], browser_secret=secret, auth=auth, telegram_id=202)
    else:
        await StaffUserService.update_staff(session, user.id, ManagerStaffUpdatePayload(telegram_id=None),
                                           tenant_scope=auth.tenant_scope(), actor_role="owner")
    assert not (await BotAccessService.get_context(session, 101)).is_staff
    assert not await StaffUserService.is_active_owner_admin_telegram_user(session, 101)
    assert await legacy_recipient_ids(session, [101]) == []
    recipients = await ManagementRecipientDirectory.list_telegram(session)
    assert "101" not in [item.destination for item in recipients]
    assert await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
        session, Installer(name="Unmapped historical contractor", telegram_id=101),
    ) is None
    # An explicit future active mapping is authoritative, not a permanent ban.
    user.telegram_id = 101
    user.primary_role, user.roles = "owner", ["owner"]
    membership = await session.scalar(select(TenantMembership))
    membership.role = "owner"
    await session.commit()
    assert (await BotAccessService.get_context(session, 101)).is_staff
    assert await StaffUserService.is_active_owner_admin_telegram_user(session, 101)


@pytest.fixture
async def telegram_client(telegram_db, monkeypatch):
    session, _, auth = telegram_db
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "existing-service-token")
    app = FastAPI()
    app.include_router(link_router)
    app.include_router(login_router)
    app.include_router(bot_router)
    async def db_session():
        yield session
    app.dependency_overrides[get_session] = db_session
    app.dependency_overrides[get_current_auth_context] = lambda: auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_link_http_cookie_and_origin_contract(telegram_client, telegram_db):
    client = telegram_client
    rejected = await client.post("/api/manager/account/telegram/link-challenges")
    assert rejected.status_code == 403
    rejected = await client.post("/api/manager/account/telegram/link-challenges", headers={
        "X-Kitlane-Telegram": "1", "Origin": "https://attacker.invalid",
    })
    assert rejected.status_code == 403
    started = await client.post("/api/manager/account/telegram/link-challenges", headers={"X-Kitlane-Telegram": "1"})
    assert started.status_code == 200
    assert "HttpOnly" in started.headers["set-cookie"]
    result = started.json()
    claimed = await client.post("/api/internal/bot/v1/account-links/claim", json={
        "token": token(result), "purpose": "link", "telegram_id": 101, "chat_id": 101, "message_id": 10,
        "telegram_display_name": "Real Telegram", "telegram_username": "real",
    }, headers={"Authorization": "Bearer existing-service-token"})
    assert claimed.status_code == 200
    status = await client.get(f"/api/manager/account/telegram/link-challenges/{result['challenge_id']}")
    assert status.json()["telegram"] == {"id": 101, "username": "real", "display_name": "Real Telegram"}
    confirmed = await client.post(f"/api/manager/account/telegram/link-challenges/{result['challenge_id']}/confirm",
                                   json={"telegram_id": 101}, headers={"X-Kitlane-Telegram": "1"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "linked"
    assert "access_token=" in confirmed.headers["set-cookie"]


@pytest.mark.asyncio
async def test_bot_http_token_and_private_sender_are_mandatory(telegram_client):
    result = await telegram_client.post("/api/internal/bot/v1/account-links/claim", json={
        "token": "a" * 43, "purpose": "link", "telegram_id": 101, "chat_id": 101, "message_id": 10,
        "telegram_display_name": "Real Telegram",
    })
    assert result.status_code == 401


@pytest.mark.asyncio
async def test_http_bot_login_only_issues_cookie_after_explicit_approval(telegram_client, telegram_db):
    session, user, _ = telegram_db
    user.telegram_id = 101
    await session.commit()
    started = await telegram_client.post("/login/telegram/challenges", headers={"X-Kitlane-Telegram": "1"})
    assert started.status_code == 200
    assert "access_token=" not in started.headers["set-cookie"]
    result = started.json()
    bot_headers = {"Authorization": "Bearer existing-service-token"}
    claimed = await telegram_client.post("/api/internal/bot/v1/account-links/claim", headers=bot_headers, json={
        "token": token(result), "purpose": "login", "telegram_id": 101, "chat_id": 101, "message_id": 10,
        "telegram_display_name": "Real Telegram",
    })
    assert claimed.status_code == 200
    status = await telegram_client.get(f"/login/telegram/challenges/{result['challenge_id']}")
    assert status.json()["status"] == "approval_pending"
    assert "set-cookie" not in status.headers
    decision = await telegram_client.post("/api/internal/bot/v1/account-links/login-decision", headers=bot_headers,
                                         json={"challenge_id": result["challenge_id"], "telegram_id": 101, "approve": True})
    assert decision.status_code == 200
    completed = await telegram_client.post(f"/login/telegram/challenges/{result['challenge_id']}/complete",
                                          headers={"X-Kitlane-Telegram": "1"})
    assert completed.status_code == 200
    assert completed.json()["token_type"] == "bearer"
    assert "access_token=" in completed.headers["set-cookie"]
