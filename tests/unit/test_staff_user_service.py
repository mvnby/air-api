from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from models import Installer, StaffUser
from services.staff_user_service import StaffUserService


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
    maintenance_executor = StaffUser(display_name="Maintenance", status="active", roles=["maintenance"])
    repair_executor = StaffUser(display_name="Repair", status="active", roles=["repair"])
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


@pytest.mark.asyncio
async def test_find_active_executors_by_role_excludes_inactive_and_blocked(sqlite_staff_session):
    sqlite_staff_session.add(
        StaffUser(display_name="Active Installer", status="active", roles=["installer"], legacy_installer_id=None)
    )
    sqlite_staff_session.add(StaffUser(display_name="Inactive Installer", status="inactive", roles=["installer"]))
    sqlite_staff_session.add(StaffUser(display_name="Blocked Installer", status="blocked", roles=["installer"]))
    sqlite_staff_session.add(StaffUser(display_name="Active Admin", status="active", roles=["admin"]))
    await sqlite_staff_session.commit()

    users = await StaffUserService.find_active_executors_by_role(
        sqlite_staff_session,
        StaffUserService.ROLE_INSTALLER,
    )

    assert [user.display_name for user in users] == ["Active Installer"]


@pytest.mark.asyncio
async def test_admin_recipients_use_active_db_owner_admin_before_legacy_fallback(sqlite_staff_session, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    sqlite_staff_session.add(StaffUser(display_name="Owner", status="active", roles=["owner"], telegram_id=101))
    sqlite_staff_session.add(StaffUser(display_name="Admin", status="active", roles=["admin"], telegram_id=202))
    sqlite_staff_session.add(StaffUser(display_name="Blocked", status="blocked", roles=["admin"], telegram_id=303))
    sqlite_staff_session.add(StaffUser(display_name="Installer", status="active", roles=["installer"], telegram_id=404))
    await sqlite_staff_session.commit()

    recipients = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(sqlite_staff_session)

    assert recipients == [101, 202]


@pytest.mark.asyncio
async def test_admin_recipients_fall_back_to_legacy_admin_ids_when_db_has_none(sqlite_staff_session, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "901,902", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 903, raising=False)

    sqlite_staff_session.add(StaffUser(display_name="Installer", status="active", roles=["installer"], telegram_id=404))
    await sqlite_staff_session.commit()

    recipients = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(sqlite_staff_session)

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
    assert staff_user.roles == ["installer"]
    assert staff_user.telegram_id == 777
