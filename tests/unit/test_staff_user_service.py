from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import hashlib
import hmac
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from models import Installer, StaffUser, TenantMembership
from services.staff_user_service import StaffUserService

from models.tenancy import TenantScope

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def sqlite_staff_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'staff.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_staff_role_and_status_helpers():
    active_admin = StaffUser(display_name="Owner", status="active", roles=["owner"], telegram_id=101)
    blocked_admin = StaffUser(display_name="Blocked", status="blocked", roles=["admin"], telegram_id=102)
    inactive_installer = StaffUser(display_name="Inactive", status="inactive", roles=["installer"])
    maintenance_executor = StaffUser(
        display_name="Maintenance",
        status="active",
        roles=["maintenance"],
        legacy_installer_id=1,
    )
    repair_executor = StaffUser(display_name="Repair", status="active", roles=["repair"], legacy_installer_id=2)
    manager = StaffUser(display_name="Manager", status="active", roles=["manager"])
    json_roles_admin = StaffUser(display_name="JSON Admin", status="active", roles='["admin"]', telegram_id=103)

    assert StaffUserService.ROLES == {
        "owner",
        "admin",
        "manager",
        "installer",
        "maintenance",
        "repair",
        "measurer",
    }
    assert StaffUserService.EXECUTOR_ROLES == {"installer", "maintenance", "repair", "measurer"}
    assert StaffUserService.has_role(active_admin, "owner")
    assert StaffUserService.can_receive_admin_notifications(active_admin)
    assert not StaffUserService.can_receive_admin_notifications(blocked_admin)
    assert not StaffUserService.can_be_executor(inactive_installer, "installer")
    assert StaffUserService.can_be_any_executor(maintenance_executor)
    assert StaffUserService.can_be_any_executor(repair_executor)
    assert not StaffUserService.can_be_any_executor(manager)
    assert StaffUserService.has_role(json_roles_admin, "admin")
    assert StaffUserService.primary_role(json_roles_admin) == "owner"


def test_staff_password_hash_and_verify():
    password_hash = StaffUserService.hash_password("secret-12345")

    assert password_hash != "secret-12345"
    assert StaffUserService.verify_password("secret-12345", password_hash)
    assert not StaffUserService.verify_password("wrong", password_hash)


def test_telegram_login_payload_signature(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", "123:token", raising=False)
    payload = {
        "id": "101",
        "first_name": "Max",
        "username": "mvn",
        "auth_date": str(int(time.time())),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(settings.BOT_TOKEN.encode("utf-8")).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    assert StaffUserService.verify_telegram_login_payload(payload)

    payload["username"] = "attacker"
    assert not StaffUserService.verify_telegram_login_payload(payload)


@pytest.mark.parametrize("bot_token", ["", StaffUserService.DISABLED_BOT_TOKEN_PLACEHOLDER])
def test_telegram_login_payload_rejects_disabled_bot_token(monkeypatch, bot_token):
    monkeypatch.setattr(settings, "BOT_TOKEN", bot_token, raising=False)
    payload = {
        "id": "101",
        "first_name": "Max",
        "auth_date": str(int(time.time())),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    assert not StaffUserService.verify_telegram_login_payload(payload)


@pytest.mark.asyncio
async def test_find_active_executors_by_role_excludes_inactive_and_blocked(sqlite_staff_session):
    installer = Installer(name="Active Legacy", is_active=True)
    sqlite_staff_session.add(installer)
    await sqlite_staff_session.flush()
    active_installer = StaffUser(
        display_name="Active Installer",
        status="active",
        roles=["installer"],
        legacy_installer_id=installer.id,
    )
    sqlite_staff_session.add(active_installer)
    sqlite_staff_session.add(StaffUser(display_name="Inactive Installer", status="inactive", roles=["installer"]))
    sqlite_staff_session.add(StaffUser(display_name="Blocked Installer", status="blocked", roles=["installer"]))
    sqlite_staff_session.add(StaffUser(display_name="Active Admin", status="active", roles=["admin"]))
    await sqlite_staff_session.flush()
    sqlite_staff_session.add(
        TenantMembership(
            tenant_id=TEST_TENANT_SCOPE.tenant_id,
            staff_user_id=int(active_installer.id or 0),
            role="installer",
            status="active",
        )
    )
    await sqlite_staff_session.commit()

    users = await StaffUserService.find_active_executors_by_role(
        sqlite_staff_session,
        StaffUserService.ROLE_INSTALLER,
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert [user.display_name for user in users] == ["Active Installer"]


@pytest.mark.asyncio
async def test_admin_recipients_use_active_db_owner_admin_before_legacy_fallback(sqlite_staff_session, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    staff_rows = [
        StaffUser(display_name="Owner", status="active", roles=["owner"], telegram_id=101),
        StaffUser(display_name="Admin", status="active", roles=["admin"], telegram_id=202),
        StaffUser(display_name="Manager", status="active", roles=["manager"], telegram_id=505),
        StaffUser(display_name="Blocked", status="blocked", roles=["admin"], telegram_id=303),
        StaffUser(display_name="Installer", status="active", roles=["installer"], telegram_id=404),
    ]
    sqlite_staff_session.add_all(staff_rows)
    await sqlite_staff_session.flush()
    for staff, role in zip(
        staff_rows,
        ("owner", "admin", "manager", "admin", "installer"),
        strict=True,
    ):
        sqlite_staff_session.add(
            TenantMembership(
                tenant_id=TEST_TENANT_SCOPE.tenant_id,
                staff_user_id=int(staff.id or 0),
                role=role,
                status="active",
            )
        )
    await sqlite_staff_session.commit()

    recipients = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(sqlite_staff_session, tenant_scope=TEST_TENANT_SCOPE)

    assert recipients == [101, 202, 505]


@pytest.mark.asyncio
async def test_admin_recipients_do_not_cross_tenant_memberships(
    sqlite_staff_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    scope_b = TenantScope(tenant_id=2, storefront_id=2, is_system=False)
    owner_a = StaffUser(
        display_name="Owner A",
        status="active",
        roles=["owner"],
        telegram_id=101,
    )
    owner_b = StaffUser(
        display_name="Owner B",
        status="active",
        roles=["owner"],
        telegram_id=202,
    )
    sqlite_staff_session.add_all([owner_a, owner_b])
    await sqlite_staff_session.flush()
    sqlite_staff_session.add_all(
        [
            TenantMembership(
                tenant_id=TEST_TENANT_SCOPE.tenant_id,
                staff_user_id=int(owner_a.id or 0),
                role="owner",
                status="active",
            ),
            TenantMembership(
                tenant_id=scope_b.tenant_id,
                staff_user_id=int(owner_b.id or 0),
                role="owner",
                status="active",
            ),
        ]
    )
    await sqlite_staff_session.commit()

    recipients_a = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
        sqlite_staff_session,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    recipients_b = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
        sqlite_staff_session,
        tenant_scope=scope_b,
    )

    assert recipients_a == [101]
    assert recipients_b == [202]


@pytest.mark.asyncio
async def test_telegram_admin_check_uses_active_owner_admin_and_blocks_non_admin_staff(
    sqlite_staff_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "404,505", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    sqlite_staff_session.add(StaffUser(display_name="Owner", status="active", roles=["owner"], telegram_id=101))
    sqlite_staff_session.add(StaffUser(display_name="Admin", status="active", roles=["admin"], telegram_id=202))
    sqlite_staff_session.add(StaffUser(display_name="Blocked", status="blocked", roles=["admin"], telegram_id=303))
    sqlite_staff_session.add(StaffUser(display_name="Manager", status="active", roles=["manager"], telegram_id=404))
    sqlite_staff_session.add(StaffUser(display_name="Inactive", status="inactive", roles=["owner"], telegram_id=505))
    await sqlite_staff_session.commit()

    assert await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 101)
    assert await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 202)
    assert not await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 303)
    assert await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 404)
    assert not await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 505)
    assert not await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 606)


@pytest.mark.asyncio
async def test_telegram_admin_check_keeps_legacy_fallback_when_no_staff_match(
    sqlite_staff_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "707", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 808, raising=False)

    sqlite_staff_session.add(StaffUser(display_name="Owner", status="active", roles=["owner"], telegram_id=101))
    await sqlite_staff_session.commit()

    assert await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 707)
    assert await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 808)
    assert not await StaffUserService.is_active_owner_admin_telegram_user(sqlite_staff_session, 909)


@pytest.mark.asyncio
async def test_telegram_admin_check_falls_back_to_legacy_when_db_lookup_fails(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "909", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))

    assert await StaffUserService.is_active_owner_admin_telegram_user(session, 909)
    assert not await StaffUserService.is_active_owner_admin_telegram_user(session, 101)


@pytest.mark.asyncio
async def test_admin_recipients_fall_back_to_legacy_admin_ids_when_db_has_none(sqlite_staff_session, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "901,902", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 903, raising=False)

    installer = StaffUser(
        display_name="Installer",
        status="active",
        roles=["installer"],
        telegram_id=404,
    )
    sqlite_staff_session.add(installer)
    await sqlite_staff_session.flush()
    sqlite_staff_session.add(
        TenantMembership(
            tenant_id=TEST_TENANT_SCOPE.tenant_id,
            staff_user_id=int(installer.id or 0),
            role="installer",
            status="active",
        )
    )
    await sqlite_staff_session.commit()

    recipients = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(sqlite_staff_session, tenant_scope=TEST_TENANT_SCOPE)

    assert recipients == [901, 902, 903]


@pytest.mark.asyncio
async def test_ensure_for_installer_creates_compatibility_staff_user(sqlite_staff_session):
    installer = Installer(name="Legacy Installer", is_active=True, default_rate=120, telegram_id=777)
    sqlite_staff_session.add(installer)
    await sqlite_staff_session.flush()

    staff_user = await StaffUserService.ensure_for_installer(sqlite_staff_session, installer)

    assert staff_user.legacy_installer_id == installer.id
    assert staff_user.display_name == "Legacy Installer"
    assert staff_user.status == "active"
    assert staff_user.primary_role == "installer"
    assert staff_user.roles == ["installer"]
    assert staff_user.telegram_id == 777


@pytest.mark.asyncio
async def test_executor_notification_telegram_prefers_active_staff_and_skips_blocked(
    sqlite_staff_session,
):
    active = Installer(name="Active Legacy", is_active=True, telegram_id=1001)
    blocked = Installer(name="Blocked Legacy", is_active=True, telegram_id=1002)
    orphan = Installer(name="Orphan Legacy", is_active=True, telegram_id=1003)
    inactive_orphan = Installer(name="Inactive Orphan", is_active=False, telegram_id=1004)
    sqlite_staff_session.add_all([active, blocked, orphan, inactive_orphan])
    await sqlite_staff_session.flush()

    sqlite_staff_session.add(
        StaffUser(
            display_name="Active Staff",
            status="active",
            roles=["installer"],
            telegram_id=2001,
            legacy_installer_id=active.id,
        )
    )
    sqlite_staff_session.add(
        StaffUser(
            display_name="Blocked Staff",
            status="blocked",
            roles=["installer"],
            telegram_id=2002,
            legacy_installer_id=blocked.id,
        )
    )
    await sqlite_staff_session.commit()

    assert await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
        sqlite_staff_session,
        active,
    ) == 2001
    assert await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
        sqlite_staff_session,
        blocked,
    ) is None
    assert await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
        sqlite_staff_session,
        orphan,
    ) == 1003
    assert await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
        sqlite_staff_session,
        inactive_orphan,
    ) is None
