from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models import OrderStageStatus
from models.tenancy import TenantScope
from services.bot_task_mutation_service import (
    BotTaskMutationConflictError,
    BotTaskMutationService,
)


TEST_TENANT_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
)


class _ScalarResult:
    def __init__(self, stage):
        self._stage = stage

    def scalars(self):
        return self

    def first(self):
        return self._stage


class _FakeSession:
    def __init__(self, stage):
        self.stage = stage
        self.statements = []
        self.added = []
        self.commit_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.stage)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_count += 1


@pytest.mark.asyncio
async def test_task_status_mutation_is_locked_idempotent_and_notifies_once(monkeypatch):
    stage = SimpleNamespace(
        id=10,
        installer_id=7,
        status=OrderStageStatus.PLANNED,
        installer_report=None,
    )
    session = _FakeSession(stage)
    get_context = AsyncMock(
        return_value=SimpleNamespace(is_staff=True, legacy_installer_id=7)
    )
    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.BotAccessService.get_context",
        get_context,
    )
    monkeypatch.setattr(
        "services.bot_task_mutation_service.NotificationService.notify_admins_work_stage_status_changed",
        notify,
    )

    first = await BotTaskMutationService.update_stage_status(
        session,
        telegram_id=777,
        stage_id=10,
        status=OrderStageStatus.IN_PROGRESS,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await BotTaskMutationService.update_stage_status(
        session,
        telegram_id=777,
        stage_id=10,
        status=OrderStageStatus.IN_PROGRESS,
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert first.changed is True
    assert repeated.changed is False
    assert stage.status == OrderStageStatus.IN_PROGRESS
    assert session.commit_count == 1
    notify.assert_awaited_once_with(
        session,
        10,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert len(session.statements) == 2
    assert all(statement._for_update_arg is not None for statement in session.statements)


@pytest.mark.asyncio
async def test_completed_task_cannot_be_reopened_by_stale_accept(monkeypatch):
    stage = SimpleNamespace(
        id=10,
        installer_id=7,
        status=OrderStageStatus.COMPLETED,
        installer_report=None,
    )
    session = _FakeSession(stage)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.BotAccessService.get_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, legacy_installer_id=7)),
    )

    with pytest.raises(BotTaskMutationConflictError):
        await BotTaskMutationService.update_stage_status(
            session,
            telegram_id=777,
            stage_id=10,
            status=OrderStageStatus.IN_PROGRESS,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert stage.status == OrderStageStatus.COMPLETED
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_task_report_mutation_is_normalized_and_idempotent(monkeypatch):
    stage = SimpleNamespace(
        id=10,
        installer_id=7,
        status=OrderStageStatus.IN_PROGRESS,
        installer_report=None,
    )
    session = _FakeSession(stage)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.BotAccessService.get_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, legacy_installer_id=7)),
    )

    first = await BotTaskMutationService.save_stage_report(
        session,
        telegram_id=777,
        stage_id=10,
        report="  Монтаж завершен  ",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await BotTaskMutationService.save_stage_report(
        session,
        telegram_id=777,
        stage_id=10,
        report="Монтаж завершен",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert first.changed is True
    assert repeated.changed is False
    assert stage.installer_report == "Монтаж завершен"
    assert session.commit_count == 1
