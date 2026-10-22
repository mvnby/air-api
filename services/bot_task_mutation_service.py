"""Staff-authorized, concurrency-safe task mutations for the Telegram API."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    OrderAttachmentLink,
    OrderStageStatus,
    OrderWorkStage,
    ServiceAttachment,
)
from models.tenancy import TenantScope
from services.order_workflow_revision import bump_order_workflow_revision
from services.bot_worker_access import BotWorkerAccessDeniedError, bot_worker_auth
from services.worker_assignment_access_service import WorkerAssignmentAccessService
from services.worker_assignment_service import WorkerAssignmentError
from services.notification_service import NotificationService
from services.service_attachment_service import ServiceAttachmentService
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


@dataclass(frozen=True)
class BotTaskAttachmentMutationResult:
    stage_id: int
    order_id: int
    already_attached: bool


class BotTaskMutationService:
    @staticmethod
    async def _authorized_stage_for_update(
        session: AsyncSession,
        *,
        telegram_id: int,
        stage_id: int,
        tenant_scope: TenantScope,
    ) -> OrderWorkStage:
        try:
            auth = await bot_worker_auth(session, telegram_id, tenant_scope)
            assignment = await WorkerAssignmentAccessService.get_for_stage(
                session, auth, stage_id, for_update=True, existing_action=True,
            )
        except (BotWorkerAccessDeniedError, WorkerAssignmentError) as exc:
            raise BotTaskMutationAccessDeniedError(str(exc)) from exc
        if assignment is None:
            raise BotTaskMutationAccessDeniedError("An active explicit work assignment is required")

        stage = await TenantEntityAccessService.get_order_stage(
            session,
            stage_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if not stage or stage.order_id != assignment.order_id:
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
        await bump_order_workflow_revision(session, int(stage.order_id))
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
        await bump_order_workflow_revision(session, int(stage.order_id))
        await session.commit()
        return BotTaskReportMutationResult(stage_id=stage_id, changed=True)

    @staticmethod
    async def _stage_attachment_exists(
        session: AsyncSession,
        *,
        stage_id: int,
        order_id: int,
        file_id: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> bool:
        filters = [
            OrderAttachmentLink.order_id == order_id,
            OrderAttachmentLink.work_stage_id == stage_id,
            OrderAttachmentLink.archived_at.is_(None),
            ServiceAttachment.archived_at.is_(None),
        ]
        if telegram_chat_id is not None and telegram_message_id is not None:
            filters.extend(
                [
                    ServiceAttachment.telegram_chat_id == telegram_chat_id,
                    ServiceAttachment.telegram_message_id == telegram_message_id,
                ]
            )
        else:
            filters.append(ServiceAttachment.telegram_file_id == file_id)
        statement = (
            select(OrderAttachmentLink.id)
            .join(
                ServiceAttachment,
                ServiceAttachment.id == OrderAttachmentLink.attachment_id,
            )
            .where(*filters)
            .limit(1)
        )
        return await session.scalar(statement) is not None

    @classmethod
    async def attach_stage_attachment(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        stage_id: int,
        file_id: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        tenant_scope: TenantScope,
    ) -> BotTaskAttachmentMutationResult:
        stage = await cls._authorized_stage_for_update(
            session,
            telegram_id=telegram_id,
            stage_id=stage_id,
            tenant_scope=tenant_scope,
        )
        order_id = int(stage.order_id)
        # The authorized stage is locked through the attachment service commit,
        # so concurrent retries serialize before this idempotency check.
        already_attached = await cls._stage_attachment_exists(
            session,
            stage_id=stage_id,
            order_id=order_id,
            file_id=file_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        await ServiceAttachmentService.create_and_link_order_attachment(
            session,
            order_id=order_id,
            content=content,
            filename=filename,
            mime_type=mime_type,
            category="service",
            source="telegram_bot",
            work_stage_id=stage_id,
            captured_at=datetime.now(),
            telegram_meta={
                "file_id": file_id,
                "user_id": telegram_id,
                "chat_id": telegram_chat_id,
                "message_id": telegram_message_id,
            },
            source_meta={
                "purpose": "task_stage_report",
                "stage_id": stage_id,
            },
            tenant_scope=tenant_scope,
        )
        return BotTaskAttachmentMutationResult(
            stage_id=stage_id,
            order_id=order_id,
            already_attached=already_attached,
        )
