from __future__ import annotations

import json

import pytest
from sqlalchemy import func
from sqlmodel import select

from models import StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
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
        username="andrey-polotsk",
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
    assert "password" not in json.dumps(plan).casefold()

    result = await TenantManagerProvisioningService.execute(
        db,
        request=request,
        password="manager-password-2026",
        plan_token=plan["plan_token"],
    )
    await db.commit()

    assert result["changed"] is True
    assert "password" not in json.dumps(result).casefold()
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
    assert any("non-manager global roles" in value for value in plan["blockers"])
    assert any("exactly one tenant membership" in value for value in plan["blockers"])
    with pytest.raises(TenantManagerProvisioningBlockedError, match="preflight"):
        await TenantManagerProvisioningService.execute(
            db,
            request=request,
            password=None,
            plan_token=plan["plan_token"],
        )


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
        }
    ]
    assert "match both username and phone" in " ".join(plan["blockers"])
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
