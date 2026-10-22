from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.sql.dml import Update

from models import Order, OrderStageStatus
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


@pytest.fixture(autouse=True)
def explicit_assignment(monkeypatch):
    assignment = AsyncMock(return_value=SimpleNamespace(order_id=42))
    monkeypatch.setattr(
        "services.bot_task_mutation_service.WorkerAssignmentAccessService.get_for_stage", assignment,
    )
    return assignment


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
        self.workflow_revision = 7
        self.events = []

    async def execute(self, statement):
        self.statements.append(statement)
        if isinstance(statement, Update):
            self.workflow_revision += 1
            self.events.append(("revision", self.workflow_revision))
            return SimpleNamespace(scalar_one=lambda: self.workflow_revision)
        return _ScalarResult(self.stage)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.events.append(("flush", self.stage.status, self.stage.installer_report))

    async def commit(self):
        self.events.append(("commit", self.workflow_revision))
        self.commit_count += 1


def _assert_single_revision_before_commit(session, status, report):
    # Exercise the real revision helper, including its flush/UPDATE/commit ordering.
    # The idempotent second call must add neither a revision nor another commit.
    assert session.workflow_revision == 8
    assert session.events == [
        ("flush", status, report),
        ("revision", 8),
        ("commit", 8),
    ]
    updates = [statement for statement in session.statements if isinstance(statement, Update)]
    assert len(updates) == 1
    statement = updates[0]
    assert statement.entity_description["entity"] is Order
    params = statement.compile().params
    assert params["workflow_revision_1"] == 1
    assert params["id_1"] == session.stage.order_id
    assert [column.name for column in statement._returning] == ["workflow_revision"]
    assert "workflow_revision +" in str(statement)


@pytest.mark.parametrize("initial_status, target_status", [
    (OrderStageStatus.PLANNED, OrderStageStatus.IN_PROGRESS),
    (OrderStageStatus.IN_PROGRESS, OrderStageStatus.COMPLETED),
])
@pytest.mark.asyncio
async def test_task_status_mutation_is_locked_idempotent_and_notifies_once(
    monkeypatch, initial_status, target_status,
):
    stage = SimpleNamespace(
        id=10,
        order_id=42,
        installer_id=7,
        status=initial_status,
        installer_report=None,
    )
    session = _FakeSession(stage)
    get_context = AsyncMock(
        return_value=SimpleNamespace(is_staff=True, legacy_installer_id=7)
    )
    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.bot_worker_auth",
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
        status=target_status,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await BotTaskMutationService.update_stage_status(
        session,
        telegram_id=777,
        stage_id=10,
        status=target_status,
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert first.changed is True
    assert repeated.changed is False
    assert stage.status == target_status
    assert session.commit_count == 1
    notify.assert_awaited_once_with(
        session,
        10,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    locks = [statement for statement in session.statements if not isinstance(statement, Update)]
    assert len(locks) == 2
    assert all(statement._for_update_arg is not None for statement in locks)
    _assert_single_revision_before_commit(session, target_status, None)


@pytest.mark.asyncio
async def test_completed_task_cannot_be_reopened_by_stale_accept(monkeypatch):
    stage = SimpleNamespace(
        id=10,
        order_id=42,
        installer_id=7,
        status=OrderStageStatus.COMPLETED,
        installer_report=None,
    )
    session = _FakeSession(stage)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.bot_worker_auth",
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
    assert session.workflow_revision == 7
    assert session.events == []


@pytest.mark.asyncio
async def test_task_report_mutation_is_normalized_and_idempotent(monkeypatch):
    stage = SimpleNamespace(
        id=10,
        order_id=42,
        installer_id=7,
        status=OrderStageStatus.IN_PROGRESS,
        installer_report=None,
    )
    session = _FakeSession(stage)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.bot_worker_auth",
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
    _assert_single_revision_before_commit(session, OrderStageStatus.IN_PROGRESS, "Монтаж завершен")


@pytest.mark.asyncio
async def test_task_attachment_uses_stage_order_and_service_provenance(monkeypatch):
    stage = SimpleNamespace(id=10, order_id=42, installer_id=7)
    session = object()
    authorize = AsyncMock(return_value=stage)
    exists = AsyncMock(return_value=False)
    create = AsyncMock(return_value={"id": 99})
    monkeypatch.setattr(
        BotTaskMutationService,
        "_authorized_stage_for_update",
        authorize,
    )
    monkeypatch.setattr(BotTaskMutationService, "_stage_attachment_exists", exists)
    monkeypatch.setattr(
        "services.bot_task_mutation_service."
        "ServiceAttachmentService.create_and_link_order_attachment",
        create,
    )

    result = await BotTaskMutationService.attach_stage_attachment(
        session,
        telegram_id=777,
        stage_id=10,
        file_id="telegram-file-10",
        filename="report.jpg",
        mime_type="image/jpeg",
        content=b"photo",
        telegram_chat_id=-100,
        telegram_message_id=55,
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert result.stage_id == 10
    assert result.order_id == 42
    assert result.already_attached is False
    authorize.assert_awaited_once_with(
        session,
        telegram_id=777,
        stage_id=10,
        tenant_scope=TEST_TENANT_SCOPE,
    )
    exists.assert_awaited_once_with(
        session,
        stage_id=10,
        order_id=42,
        file_id="telegram-file-10",
        telegram_chat_id=-100,
        telegram_message_id=55,
    )
    kwargs = create.await_args.kwargs
    assert kwargs["order_id"] == 42
    assert kwargs["work_stage_id"] == 10
    assert kwargs["category"] == "service"
    assert kwargs["source"] == "telegram_bot"
    assert kwargs["telegram_meta"] == {
        "file_id": "telegram-file-10",
        "user_id": 777,
        "chat_id": -100,
        "message_id": 55,
    }
    assert kwargs["source_meta"] == {
        "purpose": "task_stage_report",
        "stage_id": 10,
    }
