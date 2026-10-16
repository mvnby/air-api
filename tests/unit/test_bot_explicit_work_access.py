"""Old Telegram buttons cannot recover revoked or payroll-only work rights."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from models import (Installer, LegacyOwnerAuthState, Order, OrderInstaller, OrderStatus, OrderWorkStage,
                    StaffUser, Storefront, Tenant, TenantMembership, TenantWorkerProfile, OrderWorkAssignment)
from models.common import OrderStageStatus
from models.tenancy import TenantScope
from services.bot_access_service import BotAccessService
from services.bot_task_mutation_service import (BotTaskMutationAccessDeniedError, BotTaskMutationConflictError,
                                                BotTaskMutationService)


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def explicit_work(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'work.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
                         Storefront(id=1, tenant_id=1, slug="main", display_name="Main", status="active", is_default=True),
                         LegacyOwnerAuthState(), Installer(id=1, name="Historical contractor")])
        await session.flush()
        session.add(StaffUser(id=10, display_name="Worker", username="worker", primary_role="installer", roles=["installer"],
                              telegram_id=1001, legacy_installer_id=1))
        await session.flush()
        session.add(TenantMembership(id=10, tenant_id=1, staff_user_id=10, role="installer"))
        await session.flush()
        session.add_all([TenantWorkerProfile(id=10, tenant_id=1, staff_user_id=10),
                         Order(id=10, tenant_id=1, storefront_id=1, title="Secret sales title", status=OrderStatus.EXECUTION,
                               comment="CONFIDENTIAL order notes")])
        await session.flush()
        session.add_all([OrderWorkStage(id=10, order_id=10, installer_id=1, name="Secret stage title", manager_comment="PRIVATE margin",
                                       status=OrderStageStatus.PLANNED),
                         OrderInstaller(order_id=10, installer_id=1, agreed_pay=99)])
        await session.flush()
        session.add(OrderWorkAssignment(id=10, tenant_id=1, storefront_id=1, order_id=10, work_stage_id=10,
                                        worker_profile_id=10, instructions="SAFE published instructions", title="Published work"))
        await session.commit()
        monkeypatch.setattr("services.bot_task_mutation_service.NotificationService.notify_admins_work_stage_status_changed", AsyncMock())
        yield session
    await engine.dispose()


@pytest.mark.parametrize("change", ["revoke", "profile", "membership", "editor", "canceled", "closed", "no_assignment"])
@pytest.mark.parametrize("action", ["status", "report", "photo"])
async def test_old_bot_actions_deny_without_live_explicit_work_rights(explicit_work, monkeypatch, change, action):
    session = explicit_work
    if change == "revoke":
        row = await session.get(OrderWorkAssignment, 10)
        row.revoked_at = datetime.now(timezone.utc)
    elif change == "no_assignment":
        await session.delete(await session.get(OrderWorkAssignment, 10))
    elif change == "profile":
        (await session.get(TenantWorkerProfile, 10)).status = "disabled"
    elif change in {"membership", "editor"}:
        row = await session.get(TenantMembership, 10)
        if change == "membership":
            row.status = "disabled"
        else:
            row.role = "catalog_editor"
    elif change == "canceled":
        (await session.get(OrderWorkStage, 10)).status = OrderStageStatus.CANCELED
    else:
        (await session.get(Order, 10)).status = OrderStatus.CLOSED
    await session.commit()
    create_photo = AsyncMock(side_effect=AssertionError("denied photo must never persist"))
    monkeypatch.setattr("services.bot_task_mutation_service.ServiceAttachmentService.create_and_link_order_attachment", create_photo)
    with pytest.raises(BotTaskMutationAccessDeniedError):
        if action == "status":
            await BotTaskMutationService.update_stage_status(session, telegram_id=1001, stage_id=10,
                status=OrderStageStatus.IN_PROGRESS, tenant_scope=SCOPE)
        elif action == "report":
            await BotTaskMutationService.save_stage_report(session, telegram_id=1001, stage_id=10, report="Report", tenant_scope=SCOPE)
        else:
            await BotTaskMutationService.attach_stage_attachment(session, telegram_id=1001, stage_id=10,
                file_id="photo", filename="photo.jpg", mime_type="image/jpeg", content=b"photo", telegram_chat_id=1001,
                telegram_message_id=1, tenant_scope=SCOPE)
    create_photo.assert_not_awaited()


async def test_completed_explicit_stage_keeps_existing_bot_actions_without_reopening(explicit_work):
    session = explicit_work
    await BotTaskMutationService.update_stage_status(session, telegram_id=1001, stage_id=10,
        status=OrderStageStatus.COMPLETED, tenant_scope=SCOPE)
    repeated = await BotTaskMutationService.update_stage_status(session, telegram_id=1001, stage_id=10,
        status=OrderStageStatus.COMPLETED, tenant_scope=SCOPE)
    assert not repeated.changed
    report = await BotTaskMutationService.save_stage_report(session, telegram_id=1001, stage_id=10, report="Report", tenant_scope=SCOPE)
    assert report.changed
    with pytest.raises(BotTaskMutationConflictError):
        await BotTaskMutationService.update_stage_status(session, telegram_id=1001, stage_id=10,
            status=OrderStageStatus.IN_PROGRESS, tenant_scope=SCOPE)


async def test_captured_telegram_credential_version_cannot_upgrade_after_rotation(explicit_work):
    session = explicit_work
    context = await BotAccessService.get_context(session, 1001)
    session.info["bot_selection"] = context.selection
    (await session.get(StaffUser, 10)).auth_version += 1
    await session.commit()
    with pytest.raises(BotTaskMutationAccessDeniedError):
        await BotTaskMutationService.save_stage_report(session, telegram_id=1001, stage_id=10, report="Old proof", tenant_scope=SCOPE)


async def test_bot_list_uses_only_safe_published_projection_and_cabinet_url(explicit_work):
    from services.bot_task_read_service import BotTaskReadService
    from api_contracts.bot import BotTaskResponse

    tasks = await BotTaskReadService.list_for_staff(explicit_work, telegram_id=1001, limit=10, tenant_scope=SCOPE)
    assert len(tasks) == 1
    task = BotTaskResponse.model_validate(tasks[0])
    assert task.title == "Published work" and task.comment == "SAFE published instructions"
    assert task.start_time is None and task.stage_id == 10
    assert task.manager_url is None
    assert task.work_url.endswith("/my-work/10?company=1&site=main")
    assert "CONFIDENTIAL" not in str(tasks) and "PRIVATE" not in str(tasks) and "Secret" not in str(tasks)
    (await explicit_work.get(OrderWorkAssignment, 10)).revoked_at = datetime.now(timezone.utc)
    await explicit_work.commit()
    assert await BotTaskReadService.list_for_staff(explicit_work, telegram_id=1001, limit=10, tenant_scope=SCOPE) == []
