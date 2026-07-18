"""Atomically enqueue staff task notification events with CRM mutations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, Order, OrderStageStatus, OrderWorkStage
from services.bot_task_service import BotTaskService
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.staff_task_contracts import (
    STAFF_TASK_EVENT_TYPES,
    StaffTaskChangeField,
    StaffTaskEventKind,
    StaffTaskNotificationPayloadV1,
)
from services.staff_user_service import StaffUserService


class StaffTaskNotificationEventService:
    PRIORITY = 20
    MAX_ATTEMPTS = 8

    @staticmethod
    def _status_text(stage: OrderWorkStage) -> str:
        return (
            stage.status.value
            if hasattr(stage.status, "value")
            else str(stage.status)
        )

    @staticmethod
    def _idempotency_key(kind: StaffTaskEventKind, identity: list[object]) -> str:
        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"staff-task-{kind}-v1:{digest}"

    @classmethod
    async def _enqueue(
        cls,
        session: AsyncSession,
        *,
        stage: OrderWorkStage,
        installer_id: int | None,
        event_kind: StaffTaskEventKind,
        identity: list[object],
        change_fields: Iterable[StaffTaskChangeField] = (),
        reminder_offset_minutes: int | None = None,
    ) -> bool:
        if not stage.id or not installer_id:
            return False
        staff_user = await StaffUserService.get_by_legacy_installer_id(
            session,
            int(installer_id),
        )
        if (
            staff_user is None
            or staff_user.id is None
            or not StaffUserService.is_active(staff_user)
            or staff_user.telegram_id is None
        ):
            return False
        order_row = (
            await session.execute(
                select(Order.customer_id, Order.delivery_address).where(
                    Order.id == int(stage.order_id)
                )
            )
        ).one_or_none()
        if order_row is None:
            return False
        customer_row = None
        if order_row.customer_id:
            customer_row = (
                await session.execute(
                    select(Customer.name, Customer.phone).where(
                        Customer.id == int(order_row.customer_id)
                    )
                )
            ).one_or_none()
        payload = StaffTaskNotificationPayloadV1(
            event_kind=event_kind,
            staff_user_id=int(staff_user.id),
            stage_id=int(stage.id),
            order_id=int(stage.order_id),
            stage_name=stage.name,
            status=cls._status_text(stage),
            start_time=stage.start_time,
            end_time=stage.end_time,
            address=order_row.delivery_address,
            customer_name=customer_row.name if customer_row else None,
            customer_phone=customer_row.phone if customer_row else None,
            manager_url=BotTaskService._manager_url(int(stage.order_id)),
            change_fields=tuple(change_fields),
            reminder_offset_minutes=reminder_offset_minutes,
        )
        result = await IntegrationOutboxService.enqueue_with_result(
            session,
            event_type=STAFF_TASK_EVENT_TYPES[event_kind],
            aggregate_type="order_work_stage",
            aggregate_id=int(stage.id),
            payload=payload,
            idempotency_key=cls._idempotency_key(
                event_kind,
                [int(stage.id), int(staff_user.id), *identity],
            ),
            priority=cls.PRIORITY,
            max_attempts=cls.MAX_ATTEMPTS,
        )
        return result.created

    @classmethod
    async def enqueue_assigned(
        cls,
        session: AsyncSession,
        *,
        stage: OrderWorkStage,
        previous_installer_id: int | None,
    ) -> bool:
        return await cls._enqueue(
            session,
            stage=stage,
            installer_id=stage.installer_id,
            event_kind="assigned",
            identity=[previous_installer_id, stage.installer_id],
            change_fields=("assignee",),
        )

    @classmethod
    async def enqueue_rescheduled(
        cls,
        session: AsyncSession,
        *,
        stage: OrderWorkStage,
        change_fields: Iterable[StaffTaskChangeField],
        previous_values: list[object],
    ) -> bool:
        normalized_fields = tuple(dict.fromkeys(change_fields))
        if not normalized_fields:
            return False
        return await cls._enqueue(
            session,
            stage=stage,
            installer_id=stage.installer_id,
            event_kind="rescheduled",
            identity=[*previous_values, stage.start_time, stage.end_time, normalized_fields],
            change_fields=normalized_fields,
        )

    @classmethod
    async def enqueue_canceled(
        cls,
        session: AsyncSession,
        *,
        stage: OrderWorkStage,
        previous_status: object,
    ) -> bool:
        return await cls._enqueue(
            session,
            stage=stage,
            installer_id=stage.installer_id,
            event_kind="canceled",
            identity=[str(previous_status), cls._status_text(stage)],
        )

    @classmethod
    async def enqueue_address_changes(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        previous_address: str | None,
        current_address: str | None,
    ) -> int:
        if (previous_address or "").strip() == (current_address or "").strip():
            return 0
        stages = list(
            (
                await session.execute(
                    select(OrderWorkStage).where(
                        OrderWorkStage.order_id == order_id,
                        OrderWorkStage.installer_id.is_not(None),
                        OrderWorkStage.status.notin_(
                            [OrderStageStatus.CANCELED, OrderStageStatus.COMPLETED]
                        ),
                    )
                )
            ).scalars()
        )
        created = 0
        for stage in stages:
            created += int(
                await cls.enqueue_rescheduled(
                    session,
                    stage=stage,
                    change_fields=("address",),
                    previous_values=[previous_address, current_address],
                )
            )
        return created

    @classmethod
    async def enqueue_departure_reminders(
        cls,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        offset_minutes: int = 120,
        scan_window_minutes: int = 10,
    ) -> int:
        current = now or datetime.now()
        target_from = current + timedelta(minutes=max(1, int(offset_minutes)))
        target_to = target_from + timedelta(
            minutes=max(1, int(scan_window_minutes))
        )
        stages = list(
            (
                await session.execute(
                    select(OrderWorkStage).where(
                        OrderWorkStage.start_time >= target_from,
                        OrderWorkStage.start_time < target_to,
                        OrderWorkStage.installer_id.is_not(None),
                        OrderWorkStage.status.notin_(
                            [OrderStageStatus.CANCELED, OrderStageStatus.COMPLETED]
                        ),
                    )
                )
            ).scalars()
        )
        created = 0
        for stage in stages:
            created += int(
                await cls._enqueue(
                    session,
                    stage=stage,
                    installer_id=stage.installer_id,
                    event_kind="departure_reminder",
                    identity=[stage.start_time, int(offset_minutes)],
                    reminder_offset_minutes=int(offset_minutes),
                )
            )
        return created
