from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func
from sqlmodel import select

from models import StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.tenancy import TenantScope
from services.credential_service import CredentialService
from services.manager_account_credential_service import ManagerAccountCredentialService
from services.staff_user_service import StaffUserService
from services.tenant_manager_provisioning_service import (
    TenantManagerProvisioningBlockedError,
    TenantManagerProvisioningRequest,
    TenantManagerProvisioningService,
)


def _request() -> TenantManagerProvisioningRequest:
    return TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
    )


async def _seed_polotsk(db) -> tuple[Tenant, Storefront]:
    tenant = Tenant(
        slug="polotsk",
        display_name="Двина Климат",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="main",
        display_name="Двина Климат",
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    return tenant, storefront


@pytest.mark.asyncio
async def test_provisions_one_least_privilege_manager_atomically_and_idempotently(db) -> None:
    tenant, storefront = await _seed_polotsk(db)
    request = _request()

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is True
    assert plan["changes"] == ["create_staff_user", "create_active_manager_membership"]
    assert "manager-password-2026" not in json.dumps(plan)
    assert "password_hash" not in json.dumps(plan).casefold()

    result = await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password="manager-password-2026",
        plan_token=plan["plan_token"],
    )
    await db.commit()

    assert result["changed"] is True
    assert "manager-password-2026" not in json.dumps(result)
    assert "password_hash" not in json.dumps(result).casefold()
    staff = await db.scalar(select(StaffUser).where(StaffUser.username == request.username))
    memberships = list(
        (
            await db.execute(
                select(TenantMembership).where(TenantMembership.staff_user_id == staff.id)
            )
        ).scalars()
    )
    assert staff is not None
    assert staff.display_name == "Андрей"
    assert staff.phone == "+375297146293"
    assert staff.status == "active"
    assert staff.primary_role == "manager"
    assert staff.roles == ["manager"]
    assert staff.legacy_installer_id is None
    assert StaffUserService.verify_password("manager-password-2026", staff.password_hash)
    assert [(item.tenant_id, item.role, item.status) for item in memberships] == [
        (tenant.id, "manager", "active")
    ]
    assert memberships[0].tenant_id != 1
    assert storefront.tenant_id == tenant.id
    audit_events = list(
        (await db.execute(select(TenantAuditEvent))).scalars().all()
    )
    assert len(audit_events) == 1
    audit_event = audit_events[0]
    assert audit_event.tenant_id == tenant.id
    assert audit_event.storefront_id == storefront.id
    assert audit_event.actor_username == TenantManagerProvisioningService.AUDIT_ACTOR_USERNAME
    assert audit_event.action == TenantManagerProvisioningService.AUDIT_ACTION
    assert audit_event.entity_type == "staff_user"
    assert audit_event.entity_id == staff.id
    assert audit_event.change_set["membership"]["after"] == {
        "id": memberships[0].id,
        "tenant_id": tenant.id,
        "role": "manager",
        "status": "active",
    }
    assert "password" not in json.dumps(audit_event.change_set).casefold()

    no_op_plan = await TenantManagerProvisioningService.plan(db, request=request)
    no_op = await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password=None,
        plan_token=no_op_plan["plan_token"],
    )

    assert no_op_plan["ready"] is True
    assert no_op_plan["changes"] == []
    assert no_op["changed"] is False
    assert StaffUserService.verify_password("manager-password-2026", staff.password_hash)
    assert int((await db.scalar(select(func.count(TenantAuditEvent.id)))) or 0) == 1


@pytest.mark.asyncio
async def test_rejects_stale_plan_before_writing_any_manager(db) -> None:
    _, storefront = await _seed_polotsk(db)
    request = _request()
    plan = await TenantManagerProvisioningService.plan(db, request=request)
    storefront.status = "disabled"
    db.add(storefront)
    await db.flush()

    with pytest.raises(TenantManagerProvisioningBlockedError, match="stale"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password="manager-password-2026",
            plan_token=plan["plan_token"],
        )

    assert await db.scalar(select(StaffUser).where(StaffUser.username == request.username)) is None


@pytest.mark.asyncio
async def test_rejects_identity_with_another_membership_or_elevated_role(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    request = _request()
    staff = StaffUser(
        display_name=request.display_name,
        username=request.username,
        phone=request.phone,
        status="active",
        primary_role="manager",
        roles=["manager", "admin"],
        password_hash=StaffUserService.hash_password("manager-password-2026"),
    )
    db.add(staff)
    await db.flush()
    db.add_all(
        [
            TenantMembership(
                tenant_id=int(tenant.id), staff_user_id=int(staff.id), role="manager", status="active"
            ),
            TenantMembership(tenant_id=1, staff_user_id=int(staff.id), role="admin", status="active"),
        ]
    )
    await db.flush()

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is False
    assert any("extraneous global roles" in value for value in plan["blockers"])
    assert any("exactly one tenant membership" in value for value in plan["blockers"])
    with pytest.raises(TenantManagerProvisioningBlockedError, match="preflight"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password=None,
            plan_token=plan["plan_token"],
        )


@pytest.mark.asyncio
async def test_never_converts_global_admin_to_tenant_owner(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    staff = StaffUser(
        display_name="Global Admin",
        username="global.admin",
        phone=None,
        status="active",
        primary_role="admin",
        roles=["admin"],
        password_hash=CredentialService.hash_password("admin-password-2026"),
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(staff.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    request = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Global Admin",
        username="global.admin",
        role="owner",
        reset_password=True,
    )

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is False
    assert "extraneous global roles" in " ".join(plan["blockers"])
    assert plan["changes"] == []


@pytest.mark.asyncio
async def test_owner_provisioning_is_blocked_for_system_tenant(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    tenant.is_system = True
    db.add(tenant)
    await db.flush()
    request = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="System Owner",
        username="system.owner",
        role="owner",
    )

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is False
    assert "active and non-system" in " ".join(plan["blockers"])
    assert plan["changes"] == []


@pytest.mark.asyncio
async def test_blocks_passwordless_otherwise_compliant_manager_identity(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    request = _request()
    staff = StaffUser(
        display_name=request.display_name,
        username=request.username,
        phone=request.phone,
        status="active",
        primary_role="manager",
        roles=["manager"],
        password_hash=None,
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(staff.id),
            role="manager",
            status="active",
        )
    )
    await db.flush()

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is False
    assert "no password credential" in " ".join(plan["blockers"])
    assert plan["changes"] == []


@pytest.mark.asyncio
async def test_blocks_formatted_legacy_phone_collision_without_creating_duplicate(db) -> None:
    await _seed_polotsk(db)
    request = _request()
    legacy = StaffUser(
        display_name="Legacy Андрей",
        username="legacy-andrey",
        phone="8 (029) 714-62-93",
        status="active",
        primary_role="installer",
        roles=["installer"],
    )
    db.add(legacy)
    await db.flush()

    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is False
    assert plan["current"]["staff_users"] == [
        {
            "id": legacy.id,
            "username": "legacy-andrey",
            "display_name": "Legacy Андрей",
            "phone": "8 (029) 714-62-93",
            "status": "active",
            "primary_role": "installer",
            "roles": ["installer"],
            "legacy_installer_id": None,
            "telegram_id": None,
            "telegram_username": None,
            "auth_version": 1,
            "credential_changed_at": None,
            "must_change_password": False,
        }
    ]
    assert "does not match the username" in " ".join(plan["blockers"])
    with pytest.raises(TenantManagerProvisioningBlockedError, match="preflight"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password="manager-password-2026",
            plan_token=plan["plan_token"],
        )
    assert int((await db.scalar(select(func.count(StaffUser.id)))) or 0) == 1


@pytest.mark.asyncio
async def test_blocks_telegram_linked_identity_and_binds_it_into_plan_digest(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    request = _request()
    staff = StaffUser(
        display_name=request.display_name,
        username=request.username,
        phone=request.phone,
        status="active",
        primary_role="manager",
        roles=["manager"],
        password_hash=StaffUserService.hash_password("manager-password-2026"),
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(staff.id),
            role="manager",
            status="active",
        )
    )
    await db.flush()

    plan = await TenantManagerProvisioningService.plan(db, request=request)
    assert plan["ready"] is True
    assert plan["current"]["staff_users"][0]["telegram_id"] is None
    assert plan["current"]["staff_users"][0]["telegram_username"] is None

    staff.telegram_id = 123456789
    staff.telegram_username = "andrey_polotsk"
    db.add(staff)
    await db.flush()

    changed_plan = await TenantManagerProvisioningService.plan(db, request=request)
    assert changed_plan["ready"] is False
    assert changed_plan["plan_digest"] != plan["plan_digest"]
    assert changed_plan["current"]["staff_users"][0]["telegram_id"] == 123456789
    assert changed_plan["current"]["staff_users"][0]["telegram_username"] == "andrey_polotsk"
    assert "Telegram identity" in " ".join(changed_plan["blockers"])
    assert "Telegram username" in " ".join(changed_plan["blockers"])

    with pytest.raises(TenantManagerProvisioningBlockedError, match="stale"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password=None,
            plan_token=plan["plan_token"],
        )


@pytest.mark.asyncio
async def test_rolls_back_audit_and_identity_together_when_command_transaction_rolls_back(db) -> None:
    await _seed_polotsk(db)
    await db.commit()
    request = _request()
    plan = await TenantManagerProvisioningService.plan(db, request=request)

    await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password="manager-password-2026",
        plan_token=plan["plan_token"],
    )
    assert int((await db.scalar(select(func.count(StaffUser.id)))) or 0) == 1
    assert int((await db.scalar(select(func.count(TenantAuditEvent.id)))) or 0) == 1

    await db.rollback()

    assert int((await db.scalar(select(func.count(StaffUser.id)))) or 0) == 0
    assert int((await db.scalar(select(func.count(TenantAuditEvent.id)))) or 0) == 0


@pytest.mark.asyncio
async def test_creates_owner_without_fabricating_phone_and_supports_self_service(db) -> None:
    tenant, storefront = await _seed_polotsk(db)
    request = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Test1 Demo",
        username="demo.test1",
        phone=None,
        role="owner",
    )
    plan = await TenantManagerProvisioningService.plan(db, request=request)

    assert plan["ready"] is True
    assert plan["target"]["phone"] is None
    assert plan["changes"] == ["create_staff_user", "create_active_owner_membership"]
    result = await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password="simple-demo-12",
        plan_token=plan["plan_token"],
    )
    await db.commit()

    owner = await db.get(StaffUser, result["staff_user_id"])
    membership = await db.get(TenantMembership, result["membership_id"])
    assert owner is not None
    assert owner.phone is None
    assert owner.primary_role == "owner"
    assert owner.roles == ["owner"]
    assert owner.must_change_password is False
    assert membership is not None
    assert (membership.tenant_id, membership.role, membership.status) == (
        tenant.id,
        "owner",
        "active",
    )

    await ManagerAccountCredentialService.change_password(
        db,
        staff_user_id=int(owner.id),
        actor_username=str(owner.username),
        tenant_scope=TenantScope(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            is_system=False,
        ),
        current_password="simple-demo-12",
        new_password="self-service-2026",
    )
    await db.refresh(owner)
    assert CredentialService.verify_password("self-service-2026", owner.password_hash)


@pytest.mark.asyncio
async def test_promotes_exact_manager_resets_password_and_revokes_sessions(db) -> None:
    tenant, _ = await _seed_polotsk(db)
    changed_at = datetime.now(timezone.utc) - timedelta(days=1)
    staff = StaffUser(
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        status="active",
        primary_role="manager",
        roles=["manager"],
        password_hash=CredentialService.hash_password("old-password-2026"),
        password_changed_at=changed_at,
        auth_version=4,
        must_change_password=True,
    )
    db.add(staff)
    await db.flush()
    membership = TenantMembership(
        tenant_id=int(tenant.id),
        staff_user_id=int(staff.id),
        role="manager",
        status="active",
    )
    db.add(membership)
    await db.flush()
    request = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        role="owner",
        reset_password=True,
    )

    plan = await TenantManagerProvisioningService.plan(db, request=request)
    assert plan["changes"] == [
        "promote_staff_user_to_owner",
        "reset_staff_password",
    ]
    assert plan["current"]["staff_users"][0]["auth_version"] == 4
    assert (
        plan["current"]["staff_users"][0]["credential_changed_at"]
        == changed_at.isoformat()
    )
    result = await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password="new-password-2026",
        plan_token=plan["plan_token"],
    )
    await db.commit()

    await db.refresh(staff)
    await db.refresh(membership)
    assert result["changed"] is True
    assert staff.primary_role == "owner"
    assert staff.roles == ["owner"]
    assert membership.role == "owner"
    assert staff.auth_version == 5
    assert staff.password_changed_at is not None
    assert staff.password_changed_at > changed_at
    assert staff.must_change_password is False
    assert CredentialService.verify_password("new-password-2026", staff.password_hash)
    assert not CredentialService.verify_password("old-password-2026", staff.password_hash)

    audit = (
        await db.execute(
            select(TenantAuditEvent).order_by(TenantAuditEvent.id.desc()).limit(1)
        )
    ).scalar_one()
    assert audit.change_set["auth_version"] == {"before": 4, "after": 5}
    assert audit.change_set["sessions_revoked"] is True
    assert "password" not in json.dumps(audit.change_set).casefold()
    assert "hash" not in json.dumps(audit.change_set).casefold()

    no_reset = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        role="owner",
        reset_password=False,
    )
    no_op_plan = await TenantManagerProvisioningService.plan(db, request=no_reset)
    assert no_op_plan["changes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", ["auth_version", "password_changed_at"])
async def test_reset_plan_stales_on_credential_state_change(db, changed_field: str) -> None:
    tenant, _ = await _seed_polotsk(db)
    staff = StaffUser(
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        status="active",
        primary_role="owner",
        roles=["owner"],
        password_hash=CredentialService.hash_password("old-password-2026"),
        password_changed_at=datetime.now(timezone.utc) - timedelta(days=1),
        auth_version=2,
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(staff.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    request = TenantManagerProvisioningRequest.normalize(
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        role="owner",
        reset_password=True,
    )
    plan = await TenantManagerProvisioningService.plan(db, request=request)

    if changed_field == "auth_version":
        staff.auth_version += 1
    else:
        staff.password_changed_at = datetime.now(timezone.utc)
    db.add(staff)
    await db.flush()

    with pytest.raises(TenantManagerProvisioningBlockedError, match="stale"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password="new-password-2026",
            plan_token=plan["plan_token"],
        )
