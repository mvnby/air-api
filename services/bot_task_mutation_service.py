"""Staff-authorized, concurrency-safe task mutations for the Telegram API."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from models import OrderStageStatus, OrderWorkStage
from models.tenancy import TenantScope
from services.bot_access_service import BotAccessService
from services.notification_service import NotificationService
from services.tenant_entity_access_service import TenantEntityAccessService

logger = logging.getLogger(__name__)


class BotTaskMutationAccessDeniedError(PermissionError):
    """The Telegram identity cannot mutate the requested stage."""


class BotTaskMutationConflictError(RuntimeError):
    """The requested transition conflicts with a terminal stage state."""


@dataclass(frozen=True)
class BotTaskStatusMutationResult:
    stage_id: int
    status: OrderStageStatus
    changed: bool


@dataclass(frozen=True)
class BotTaskReportMutationResult:
    stage_id: int
    changed: bool


class BotTaskMutationService:
    @staticmethod
    async def _authorized_stage_for_update(
        session: AsyncSession,
        *,
        telegram_id: int,
        stage_id: int,
        tenant_scope: TenantScope,
    ) -> OrderWorkStage:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff or not context.legacy_installer_id:
            raise BotTaskMutationAccessDeniedError("Staff task access is required")

        stage = await TenantEntityAccessService.get_order_stage(
            session,
            stage_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if not stage or stage.installer_id != context.legacy_installer_id:
            raise BotTaskMutationAccessDeniedError(
                "Task was not found or is assigned to another executor"
            )
        return stage

    @classmethod
    async def update_stage_status(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        stage_id: int,
        status: OrderStageStatus,
        tenant_scope: TenantScope,
    ) -> BotTaskStatusMutationResult:
        if status not in {OrderStageStatus.IN_PROGRESS, OrderStageStatus.COMPLETED}:
            raise ValueError("Bot may only accept or complete a task")

        stage = await cls._authorized_stage_for_update(
            session,
            telegram_id=telegram_id,
            stage_id=stage_id,
            tenant_scope=tenant_scope,
        )
        current_status = OrderStageStatus(stage.status)
        if current_status == status:
            return BotTaskStatusMutationResult(
                stage_id=stage_id,
                status=status,
                changed=False,
            )
        if current_status == OrderStageStatus.CANCELED:
            raise BotTaskMutationConflictError("Canceled task cannot be changed by the bot")
        if current_status == OrderStageStatus.COMPLETED:
            raise BotTaskMutationConflictError(
                "Completed task cannot be reopened by a stale bot action"
            )

        stage.status = status
        session.add(stage)
        await session.commit()
        try:
            await NotificationService.notify_admins_work_stage_status_changed(
                session,
                stage_id,
                tenant_scope=tenant_scope,
            )
        except Exception:
            logger.exception("BOT_TASK_STATUS_NOTIFY_FAILED stage_id=%s", stage_id)
        return BotTaskStatusMutationResult(
            stage_id=stage_id,
            status=status,
            changed=True,
        )

    @classmethod
    async def save_stage_report(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        stage_id: int,
        report: str,
        tenant_scope: TenantScope,
    ) -> BotTaskReportMutationResult:
        normalized_report = report.strip()
        if not normalized_report:
            raise ValueError("Task report must not be empty")

        stage = await cls._authorized_stage_for_update(
            session,
            telegram_id=telegram_id,
            stage_id=stage_id,
            tenant_scope=tenant_scope,
        )
        if (stage.installer_report or "").strip() == normalized_report:
            return BotTaskReportMutationResult(stage_id=stage_id, changed=False)

        stage.installer_report = normalized_report
        session.add(stage)
        await session.commit()
        return BotTaskReportMutationResult(stage_id=stage_id, changed=True)
