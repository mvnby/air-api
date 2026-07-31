from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Installer, Order, OrderInstaller, StaffUser, TenantMembership
from schemas import ManagerOrderUpdatePayload
from services.installer_service import ManagerInstallerService
from services.order_service import OrderService

from models.tenancy import TenantScope

TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def _add_tenant_staff(
    session: AsyncSession,
    staff_user: StaffUser,
    *,
    membership_status: str = "active",
) -> None:
    session.add(staff_user)
    await session.flush()
    session.add(
        TenantMembership(
            tenant_id=TEST_TENANT_SCOPE.tenant_id,
            staff_user_id=int(staff_user.id or 0),
            role="installer",
            status=membership_status,
        )
    )


@pytest.fixture
async def sqlite_installer_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'installers.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_installer_search_uses_staff_user_status_and_keeps_orphan_legacy_fallback(sqlite_installer_session):
    active = Installer(name="Active Legacy", is_active=True)
    blocked = Installer(name="Blocked Legacy", is_active=True)
    inactive = Installer(name="Inactive Legacy", is_active=True)
    orphan = Installer(name="Orphan Legacy", is_active=True)
    sqlite_installer_session.add_all([active, blocked, inactive, orphan])
    await sqlite_installer_session.flush()

    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Active Staff",
            status="active",
            roles=["installer"],
            legacy_installer_id=active.id,
        )
    )
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Blocked Staff",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=blocked.id,
        ),
        membership_status="suspended",
    )
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Inactive Staff",
            status="inactive",
            roles=["installer"],
            legacy_installer_id=inactive.id,
        ),
        membership_status="disabled",
    )
    await sqlite_installer_session.commit()

    result = await ManagerInstallerService.search(sqlite_installer_session, q="Staff", limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert [item.name for item in result.items] == ["Active Staff"]

    fallback_result = await ManagerInstallerService.search(sqlite_installer_session, q="Orphan", limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert [item.name for item in fallback_result.items] == ["Orphan Legacy"]

    legacy_name_result = await ManagerInstallerService.search(sqlite_installer_session, q="Active Legacy", limit=10, tenant_scope=TEST_TENANT_SCOPE)

    assert [item.name for item in legacy_name_result.items] == ["Active Staff"]


@pytest.mark.asyncio
async def test_installer_list_keeps_historical_blocked_staff_visible(sqlite_installer_session):
    installer = Installer(name="Legacy Name", is_active=True)
    sqlite_installer_session.add(installer)
    await sqlite_installer_session.flush()
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Blocked Historical",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=installer.id,
        ),
        membership_status="suspended",
    )
    await sqlite_installer_session.commit()

    result = await ManagerInstallerService.get_all(sqlite_installer_session, tenant_scope=TEST_TENANT_SCOPE)

    assert len(result.items) == 1
    assert result.items[0].name == "Blocked Historical"
    assert result.items[0].is_active is False


@pytest.mark.asyncio
async def test_new_order_assignment_rejects_blocked_staff_user(sqlite_installer_session):
    installer = Installer(name="Blocked Installer", is_active=True)
    order = Order(tenant_id=1, storefront_id=1)
    sqlite_installer_session.add(installer)
    sqlite_installer_session.add(order)
    await sqlite_installer_session.flush()
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Blocked Installer",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=installer.id,
        )
    )
    await sqlite_installer_session.commit()

    with pytest.raises(ValueError, match="inactive or blocked"):
        await OrderService.update_order_installers(
            sqlite_installer_session,
            order.id,
            [{"installer_id": installer.id, "agreed_pay": 100}],
            tenant_scope=TEST_TENANT_SCOPE,
        )


@pytest.mark.asyncio
async def test_new_order_assignment_notification_uses_active_staff_telegram_id(
    sqlite_installer_session,
    monkeypatch,
):
    installer = Installer(name="Active Installer", is_active=True, telegram_id=1001)
    order = Order(tenant_id=1, storefront_id=1, delivery_address="Vitebsk")
    sqlite_installer_session.add(installer)
    sqlite_installer_session.add(order)
    await sqlite_installer_session.flush()
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Active Staff",
            status="active",
            roles=["installer"],
            telegram_id=2001,
            legacy_installer_id=installer.id,
        )
    )
    await sqlite_installer_session.commit()

    notify_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("services.bot_service.BotService.notify_installer_new_order", notify_mock)

    await OrderService.update_order_installers(
        sqlite_installer_session,
        order.id,
        [{"installer_id": installer.id, "agreed_pay": 100}],
        tenant_scope=TEST_TENANT_SCOPE,
    )

    notify_mock.assert_awaited_once()
    assert notify_mock.await_args.kwargs["installer_tg_id"] == 2001


@pytest.mark.asyncio
async def test_existing_historical_blocked_assignment_can_still_update(sqlite_installer_session):
    installer = Installer(name="Historical Installer", is_active=True)
    order = Order(tenant_id=1, storefront_id=1)
    sqlite_installer_session.add(installer)
    sqlite_installer_session.add(order)
    await sqlite_installer_session.flush()
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Historical Installer",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=installer.id,
        )
    )
    sqlite_installer_session.add(
        OrderInstaller(
            order_id=order.id,
            installer_id=installer.id,
            agreed_pay=50,
        )
    )
    await sqlite_installer_session.commit()

    await OrderService.update_order_installers(
        sqlite_installer_session,
        order.id,
        [{"installer_id": installer.id, "agreed_pay": 125}],
        tenant_scope=TEST_TENANT_SCOPE,
    )

    link = await sqlite_installer_session.get(OrderInstaller, (order.id, installer.id))
    assert link is not None
    assert link.agreed_pay == 125


@pytest.mark.asyncio
async def test_new_manager_measurer_assignment_rejects_blocked_staff_user(sqlite_installer_session):
    installer = Installer(name="Blocked Measurer", is_active=True)
    order = Order(tenant_id=1, storefront_id=1, comment="before")
    sqlite_installer_session.add(installer)
    sqlite_installer_session.add(order)
    await sqlite_installer_session.flush()
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Blocked Measurer",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=installer.id,
        )
    )
    await sqlite_installer_session.commit()

    with pytest.raises(ValueError, match="inactive or blocked"):
        await OrderService.update_order_for_manager(
            sqlite_installer_session,
            order.id,
            ManagerOrderUpdatePayload(measurer_id=installer.id),
            tenant_scope=TEST_TENANT_SCOPE,
        )


@pytest.mark.asyncio
async def test_unchanged_historical_blocked_measurer_can_still_save(sqlite_installer_session):
    installer = Installer(name="Historical Measurer", is_active=True)
    order = Order(tenant_id=1, storefront_id=1, measurer_id=None, comment="before")
    sqlite_installer_session.add(installer)
    sqlite_installer_session.add(order)
    await sqlite_installer_session.flush()
    order.measurer_id = installer.id
    await _add_tenant_staff(
        sqlite_installer_session,
        StaffUser(
            display_name="Historical Measurer",
            status="blocked",
            roles=["installer"],
            legacy_installer_id=installer.id,
        )
    )
    await sqlite_installer_session.commit()

    data = await OrderService.update_order_for_manager(
        sqlite_installer_session,
        order.id,
        ManagerOrderUpdatePayload(measurer_id=installer.id, comment="after"),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert data is not None
    assert data["measurer_id"] == installer.id
    assert data["comment"] == "after"
