"""PostgreSQL proof of one-use browser completion and unique Telegram bindings."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.security import AuthenticatedUser
from models import StaffUser, TenantMembership
from services.staff_telegram_service import StaffTelegramService as Telegram
from services.staff_telegram_security import StaffTelegramError
from services.credential_service import CredentialService


async def _identity(session, index):
    user = StaffUser(display_name=f"Telegram user {index}", username=f"telegram-user-{index}",
                     primary_role="manager", roles=["manager"])
    session.add(user)
    await session.flush()
    session.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager"))
    await session.commit()
    auth = AuthenticatedUser(username=user.username, staff_user_id=user.id, auth_source="staff_password",
                             auth_version=user.auth_version, role="manager", tenant_id=1, storefront_id=1,
                             is_system_tenant=True)
    return user, auth


async def _claim(session, result, purpose):
    raw = result["deep_link"].split("?start=", 1)[1].split("_", 1)[1]
    await Telegram.claim(session, token=raw, purpose=purpose, telegram_id=101, chat_id=101,
                         message_id=10, telegram_username="real", telegram_display_name="Real Telegram")


@pytest.mark.asyncio
async def test_concurrent_login_completion_consumes_approval_once(db_engine, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "kitlane_test_bot")
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        user, _ = await _identity(session, 1)
        user.telegram_id = 101
        await session.commit()
        result, secret = await Telegram.start(session, purpose="login", browser_secret=None)
        await _claim(session, result, "login")
        await Telegram.decide(session, challenge_id=result["challenge_id"], telegram_id=101, approve=True)

    async def finish():
        async with sessions() as session:
            try:
                await Telegram.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)
                return "completed"
            except StaffTelegramError as exc:
                await session.rollback()
                return exc.code

    outcomes = await asyncio.wait_for(asyncio.gather(finish(), finish()), timeout=15)
    assert sorted(outcomes) == ["completed", "telegram_challenge_used"]


@pytest.mark.asyncio
async def test_concurrent_self_links_never_merge_or_steal_the_same_telegram(db_engine, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "kitlane_test_bot")
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    proofs = []
    async with sessions() as session:
        for index in (1, 2):
            _, auth = await _identity(session, index)
            result, secret = await Telegram.start(session, purpose="link", browser_secret=None, auth=auth)
            await _claim(session, result, "link")
            proofs.append((auth, result, secret))

    async def finish(proof):
        auth, result, secret = proof
        async with sessions() as session:
            try:
                await Telegram.confirm(session, challenge_id=result["challenge_id"], browser_secret=secret,
                                       auth=auth, telegram_id=101)
                return "linked"
            except StaffTelegramError as exc:
                await session.rollback()
                return exc.code

    outcomes = await asyncio.wait_for(asyncio.gather(*(finish(proof) for proof in proofs)), timeout=15)
    assert sorted(outcomes) == ["linked", "telegram_already_linked"]
    async with sessions() as session:
        users = list((await session.execute(select(StaffUser))).scalars())
        assert len([user for user in users if user.telegram_id == 101]) == 1
        assert all(user.merged_into_staff_user_id is None for user in users)


@pytest.mark.asyncio
async def test_widget_and_disconnect_serialize_without_upgrading_signed_proof_version(db_engine, monkeypatch):
    import services.staff_telegram_widget as widget
    from services.staff_user_service import StaffUserService
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        user, auth = await _identity(session, 1)
        user.telegram_id = 101
        user.password_hash = CredentialService.hash_password("test-password-123")
        await session.commit()
    monkeypatch.setattr(StaffUserService, "verify_telegram_login_payload", classmethod(lambda cls, payload: True))
    held, disconnect_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_consume = widget.consume_widget_proof
    async def consume_under_identity_lock(session, payload, *, commit=True):
        held.set()
        await release.wait()
        await original_consume(session, payload, commit=commit)
    monkeypatch.setattr(widget, "consume_widget_proof", consume_under_identity_lock)
    async def login():
        async with sessions() as session:
            return await widget.authenticate_widget(session, {"id": 101, "hash": "valid-signed-proof"})
    async def disconnect():
        async with sessions() as session:
            disconnect_started.set()
            return await Telegram.disconnect(session, auth=auth, current_password="test-password-123")
    login_task = asyncio.create_task(login())
    await asyncio.wait_for(held.wait(), timeout=10)
    disconnect_task = asyncio.create_task(disconnect())
    await asyncio.wait_for(disconnect_started.wait(), timeout=10)
    release.set()
    authentication, disconnected = await asyncio.wait_for(asyncio.gather(login_task, disconnect_task), timeout=15)
    assert authentication.auth_version == 1
    assert disconnected.auth_version == 2
    assert disconnected.telegram_id is None
