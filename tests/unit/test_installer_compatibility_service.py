from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Installer, LegacyOwnerAuthState, Order, OrderInstaller, StaffUser, TenantAuditEvent, TenantMembership, Tenant, Storefront
from schemas import ManagerInstallerCreatePayload, ManagerInstallerUpdatePayload, ManagerOrderUpdatePayload, ManagerStaffCreatePayload
from services.installer_service import ManagerInstallerService
from services.order_service import OrderService
from services.staff_access_policy import StaffAccessPolicyError
from services.staff_user_service import StaffUserService
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityError

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
        session.add(Tenant(id=1, slug="mvn", display_name="MVN", is_system=True))
        await session.flush()
        session.add(Storefront(id=1, tenant_id=1, slug="main", display_name="Main", status="active"))
        session.add(LegacyOwnerAuthState())
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_installer_updates_use_staff_membership_and_audit(sqlite_installer_session):
    created = await ManagerInstallerService.create(
        sqlite_installer_session,
        ManagerInstallerCreatePayload(name="Contractor", telegram_id=501),
        tenant_scope=TEST_TENANT_SCOPE, actor_role="admin", actor_username="admin",
    )
    updated = await ManagerInstallerService.update(
        sqlite_installer_session, created.id,
        ManagerInstallerUpdatePayload(name="Renamed", telegram_id=502, default_rate=150, is_active=False),
        tenant_scope=TEST_TENANT_SCOPE, actor_role="admin", actor_username="admin",
    )
    assert updated.name == "Renamed"
    assert updated.telegram_id == 502
    assert updated.default_rate == 150
    assert updated.is_active is False
    staff = await StaffUserService.get_by_legacy_installer_id(sqlite_installer_session, created.id)
    assert staff.status == "inactive"
    assert staff.primary_role == "installer"
    assert staff.roles == ["installer"]
    installer = await sqlite_installer_session.get(Installer, created.id)
    assert (installer.name, installer.telegram_id, installer.is_active) == ("Renamed", 502, False)
    events = list((await sqlite_installer_session.execute(
        select(TenantAuditEvent).order_by(TenantAuditEvent.id)
    )).scalars())
    assert events[-1].actor_username == "admin"
    assert events[-1].change_set["membership"]["after"]["status"] == "disabled"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize("changes", [{"is_active": False}, {"telegram_id": 909}])
async def test_installer_admin_cannot_disable_or_rebind_privileged_staff(sqlite_installer_session, role, changes):
    staff = await StaffUserService.create_staff(
        sqlite_installer_session,
        ManagerStaffCreatePayload(display_name="Privileged installer", primary_role=role,
                                  telegram_id=808, is_assignable_installer=True),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    with pytest.raises(StaffAccessPolicyError) as exc:
        await ManagerInstallerService.update(
            sqlite_installer_session, staff.legacy_installer_id,
            ManagerInstallerUpdatePayload(**changes),
            tenant_scope=TEST_TENANT_SCOPE, actor_role="admin",
        )
    assert exc.value.code == "staff_role_forbidden"
    await sqlite_installer_session.rollback()
    identity = await sqlite_installer_session.get(StaffUser, staff.id)
    assert identity.telegram_id == 808
    assert identity.status == "active"


@pytest.mark.asyncio
async def test_installer_path_preserves_last_active_owner(sqlite_installer_session):
    owner = await StaffUserService.create_staff(
        sqlite_installer_session,
        ManagerStaffCreatePayload(display_name="Only owner", primary_role="owner", is_assignable_installer=True),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    with pytest.raises(StaffAccessPolicyError) as exc:
        await ManagerInstallerService.update(
            sqlite_installer_session, owner.legacy_installer_id,
            ManagerInstallerUpdatePayload(is_active=False),
            tenant_scope=TEST_TENANT_SCOPE, actor_role="owner",
        )
    assert exc.value.code == "last_active_owner"
    await sqlite_installer_session.rollback()
    membership = (await sqlite_installer_session.execute(select(TenantMembership).where(
        TenantMembership.staff_user_id == owner.id,
    ))).scalar_one()
    assert membership.status == "active"


@pytest.mark.asyncio
async def test_installer_path_preserves_bound_legacy_owner_fence(sqlite_installer_session):
    owner = await StaffUserService.create_staff(
        sqlite_installer_session,
        ManagerStaffCreatePayload(display_name="Bound owner", primary_role="owner", is_assignable_installer=True),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    state = await sqlite_installer_session.get(LegacyOwnerAuthState, 1)
    state.owner_staff_user_id = owner.id
    await sqlite_installer_session.commit()
    with pytest.raises(LegacyOwnerManagedIdentityError):
        await ManagerInstallerService.update(
            sqlite_installer_session, owner.legacy_installer_id,
            ManagerInstallerUpdatePayload(telegram_id=909),
            tenant_scope=TEST_TENANT_SCOPE, actor_role="owner", is_platform_owner=True,
        )


@pytest.mark.asyncio
async def test_unmapped_legacy_installer_can_be_adopted_and_disabled(sqlite_installer_session):
    contractor = Installer(name="Legacy contractor", telegram_id=707)
    sqlite_installer_session.add(contractor)
    await sqlite_installer_session.commit()
    result = await ManagerInstallerService.update(
        sqlite_installer_session, contractor.id, ManagerInstallerUpdatePayload(is_active=False),
        tenant_scope=TEST_TENANT_SCOPE, actor_role="admin",
    )
    assert result.name == "Legacy contractor"
    assert result.is_active is False
    staff = await StaffUserService.get_by_legacy_installer_id(sqlite_installer_session, contractor.id)
    assert staff.primary_role == "installer"
    assert staff.telegram_id == 707
    assert staff.status == "inactive"


@pytest.mark.asyncio
async def test_installer_status_keeps_other_tenant_access_active(sqlite_installer_session):
    installer = await ManagerInstallerService.create(
        sqlite_installer_session, ManagerInstallerCreatePayload(name="Shared contractor"),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    staff = await StaffUserService.get_by_legacy_installer_id(sqlite_installer_session, installer.id)
    sqlite_installer_session.add(TenantMembership(
        tenant_id=2, staff_user_id=staff.id, role="installer", status="active",
    ))
    await sqlite_installer_session.commit()
    result = await ManagerInstallerService.update(
        sqlite_installer_session, installer.id, ManagerInstallerUpdatePayload(is_active=False),
        tenant_scope=TEST_TENANT_SCOPE, actor_role="admin",
    )
    assert result.is_active is False
    await sqlite_installer_session.refresh(staff)
    assert staff.status == "active"
    assert staff.roles == ["installer"]
    legacy = await sqlite_installer_session.get(Installer, installer.id)
    assert legacy.is_active is True


@pytest.mark.asyncio
async def test_installer_guard_refreshes_membership_after_waiting_for_lock(sqlite_installer_session):
    installer = await ManagerInstallerService.create(
        sqlite_installer_session, ManagerInstallerCreatePayload(name="Promoted contractor"),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    staff = await StaffUserService.get_by_legacy_installer_id(sqlite_installer_session, installer.id)
    cached_membership = (await sqlite_installer_session.execute(select(TenantMembership).where(
        TenantMembership.staff_user_id == staff.id,
    ))).scalar_one()
    # A different transaction promotes the target after the request has read it.
    async with AsyncSession(bind=sqlite_installer_session.bind) as another_session:
        membership = await another_session.get(TenantMembership, cached_membership.id)
        membership.role = "owner"
        await another_session.commit()
    assert cached_membership.role == "installer"
    with pytest.raises(StaffAccessPolicyError) as exc:
        await ManagerInstallerService.update(
            sqlite_installer_session, installer.id, ManagerInstallerUpdatePayload(telegram_id=909),
            tenant_scope=TEST_TENANT_SCOPE, actor_role="admin",
        )
    assert exc.value.code == "staff_role_forbidden"


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
