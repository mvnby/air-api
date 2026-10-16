"""Transactional commands for order work stages and their outbox events."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models import Order, OrderAttachmentLink, OrderStageStatus, OrderStatus, OrderWorkStage
from services.command_transaction import command_transaction
from services.worker_assignment_legacy_sync import WorkerAssignmentLegacySync
from services.order_projection_service import OrderProjectionService
from services.order_service import OrderService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class OrderWorkStageCommandService:
    @staticmethod
    async def _get_stage_for_update(session, stage_id, *, tenant_scope, order_id=None, for_update=True):
        # Match the assignment/Bot lock order. A joined Stage+Order FOR UPDATE
        # cannot guarantee which row lock PostgreSQL acquires first.
        hint = await TenantEntityAccessService.get_order_stage(
            session, stage_id, tenant_scope=tenant_scope, order_id=order_id,
        )
        if hint is None:
            return None
        order = await TenantEntityAccessService.get_order(
            session, hint.order_id, tenant_scope=tenant_scope, for_update=True,
        )
        if order is None:
            return None
        return await session.scalar(select(OrderWorkStage).where(
            OrderWorkStage.id == stage_id, OrderWorkStage.order_id == order.id,
        ).with_for_update().execution_options(populate_existing=True))

    @staticmethod
    async def _project_committed_order(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        data = await OrderProjectionService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if data is None:
            raise RuntimeError("Committed order is no longer visible in its tenant scope")
        return data

    @staticmethod
    async def add_order_stage(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        from services.staff_task_notification_event_service import (
            StaffTaskNotificationEventService,
        )

        async with command_transaction(session):
            worker_profiles = await WorkerAssignmentLegacySync.prepare(session, tenant_scope, [payload.installer_id])
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not order:
                raise ValueError("Order not found")
            if payload.installer_id is not None:
                await OrderService._ensure_assignable_legacy_executor(
                    session,
                    int(payload.installer_id),
                    tenant_scope=tenant_scope,
                )
            stage = OrderWorkStage(
                order_id=order_id,
                name=payload.name,
                status=OrderService._normalize_order_stage_status(payload.status),
                start_time=OrderService._normalize_naive_datetime(payload.start_time),
                end_time=OrderService._normalize_naive_datetime(payload.end_time),
                installer_id=payload.installer_id,
                manager_comment=payload.manager_comment,
                installer_report=payload.installer_report,
            )
            session.add(stage)
            await session.flush()
            await WorkerAssignmentLegacySync.sync(session, tenant_scope, order_id, worker_profiles, previous_ids=set(), current_ids={stage.installer_id} - {None}, stage=stage)
            if stage.installer_id is not None:
                await StaffTaskNotificationEventService.enqueue_assigned(
                    session,
                    stage=stage,
                    previous_installer_id=None,
                    tenant_scope=tenant_scope,
                )

        return await OrderWorkStageCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def cancel_order_stage_direct(
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        from services.staff_task_notification_event_service import (
            StaffTaskNotificationEventService,
        )

        async with command_transaction(session):
            await WorkerAssignmentLegacySync.prepare(session, tenant_scope)
            stage = await OrderWorkStageCommandService._get_stage_for_update(
                session,
                stage_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not stage:
                raise ValueError("Stage not found")
            previous_status = stage.status
            stage.status = OrderStageStatus.CANCELED
            session.add(stage)
            if previous_status != OrderStageStatus.CANCELED:
                await StaffTaskNotificationEventService.enqueue_canceled(
                    session,
                    stage=stage,
                    previous_status=previous_status,
                    tenant_scope=tenant_scope,
                )

        stage = await TenantEntityAccessService.get_order_stage(
            session,
            stage_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(OrderWorkStage.order).selectinload(Order.customer),
                selectinload(OrderWorkStage.installer),
            ),
        )
        if stage is None:
            raise ValueError("Stage not found")
        return OrderService._map_stale_order_stage(stage)

    @staticmethod
    async def delete_order_stage_direct(
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            await WorkerAssignmentLegacySync.prepare(session, tenant_scope)
            stage = await OrderWorkStageCommandService._get_stage_for_update(
                session,
                stage_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not stage:
                raise ValueError("Stage not found")
            from services.installer_collection_service import InstallerCollectionService
            await InstallerCollectionService.withdraw_for_stage(
                session, tenant_scope, stage.order_id, stage.id,
            )
            await session.execute(update(OrderAttachmentLink).where(
                OrderAttachmentLink.order_id == stage.order_id,
                OrderAttachmentLink.work_stage_id == stage.id,
            ).values(work_stage_id=None))
            await session.delete(stage)
        return {"ok": True, "id": stage_id}

    @staticmethod
    async def update_order_stage(
        session: AsyncSession,
        order_id: int,
        stage_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        from services.staff_task_notification_event_service import (
            StaffTaskNotificationEventService,
        )

        async with command_transaction(session):
            worker_profiles = await WorkerAssignmentLegacySync.prepare(session, tenant_scope, [getattr(payload, "installer_id", None)])
            stage = await OrderWorkStageCommandService._get_stage_for_update(
                session,
                stage_id,
                tenant_scope=tenant_scope,
                order_id=order_id,
                for_update=True,
            )
            if not stage:
                raise ValueError("Stage not found")
            previous_installer_id = stage.installer_id
            previous_start_time = stage.start_time
            previous_end_time = stage.end_time
            previous_status = stage.status
            update_data = payload.model_dump(exclude_unset=True)
            next_installer_id = update_data.get("installer_id", stage.installer_id)
            if (
                next_installer_id is not None
                and next_installer_id != stage.installer_id
            ):
                await OrderService._ensure_assignable_legacy_executor(
                    session,
                    int(next_installer_id),
                    tenant_scope=tenant_scope,
                )
            for key, value in update_data.items():
                if key in ("start_time", "end_time"):
                    value = OrderService._normalize_naive_datetime(value)
                elif key == "status":
                    value = OrderService._normalize_order_stage_status(value)
                setattr(stage, key, value)

            session.add(stage)
            await session.flush()
            await WorkerAssignmentLegacySync.sync(session, tenant_scope, order_id, worker_profiles, previous_ids={previous_installer_id} - {None}, current_ids={stage.installer_id} - {None}, stage=stage)

            if (
                stage.status == OrderStageStatus.CANCELED
                and previous_status != OrderStageStatus.CANCELED
            ):
                await StaffTaskNotificationEventService.enqueue_canceled(
                    session,
                    stage=stage,
                    previous_status=previous_status,
                    tenant_scope=tenant_scope,
                )
            elif (
                stage.installer_id != previous_installer_id
                and stage.installer_id is not None
            ):
                await StaffTaskNotificationEventService.enqueue_assigned(
                    session,
                    stage=stage,
                    previous_installer_id=previous_installer_id,
                    tenant_scope=tenant_scope,
                )
            elif stage.installer_id is not None:
                changed_fields = []
                previous_values = []
                if stage.start_time != previous_start_time:
                    changed_fields.append("start_time")
                    previous_values.extend([previous_start_time, stage.start_time])
                if stage.end_time != previous_end_time:
                    changed_fields.append("end_time")
                    previous_values.extend([previous_end_time, stage.end_time])
                if changed_fields:
                    await StaffTaskNotificationEventService.enqueue_rescheduled(
                        session,
                        stage=stage,
                        change_fields=changed_fields,
                        previous_values=previous_values,
                        tenant_scope=tenant_scope,
                    )

            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            if order:
                await session.refresh(order, attribute_names=["work_stages"])
                all_completed = all(
                    item.status
                    in (OrderStageStatus.COMPLETED, OrderStageStatus.CANCELED)
                    for item in order.work_stages
                )
                if (
                    all_completed
                    and order.work_stages
                    and order.balance_due > 0
                    and order.status != OrderStatus.CLOSED
                ):
                    order.is_on_hold = True
                    order.on_hold_reason = (
                        "Все запланированные этапы завершены, ожидается оплата "
                        "или следующий этап"
                    )
                    session.add(order)

        return await OrderWorkStageCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def delete_order_stage(
        session: AsyncSession,
        order_id: int,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            await WorkerAssignmentLegacySync.prepare(session, tenant_scope)
            stage = await OrderWorkStageCommandService._get_stage_for_update(
                session,
                stage_id,
                tenant_scope=tenant_scope,
                order_id=order_id,
                for_update=True,
            )
            if not stage:
                raise ValueError("Stage not found")
            from services.installer_collection_service import InstallerCollectionService
            await InstallerCollectionService.withdraw_for_stage(
                session, tenant_scope, stage.order_id, stage.id,
            )
            await session.execute(update(OrderAttachmentLink).where(
                OrderAttachmentLink.order_id == stage.order_id,
                OrderAttachmentLink.work_stage_id == stage.id,
            ).values(work_stage_id=None))
            await session.delete(stage)

        return await OrderWorkStageCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
