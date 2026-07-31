from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    Order,
    OrderInstaller,
    OrderStageStatus,
    OrderStatus,
    OrderWorkStage,
    StaffUser,
    TenantMembership,
)
from models.tenancy import TenantScope
from services.staff_user_service import StaffUserService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_or_fully_legacy_scope_clause


class BotTaskService:
    ACTIVE_ORDER_STATUSES = {
        OrderStatus.NEW_LEAD,
        OrderStatus.NEGOTIATION,
        OrderStatus.EXECUTION,
    }

    @staticmethod
    async def _staff_by_telegram_id(
        session: AsyncSession,
        telegram_id: int | str | None,
        *,
        tenant_scope: TenantScope,
    ) -> StaffUser | None:
        try:
            normalized_telegram_id = int(telegram_id) if telegram_id is not None else 0
        except (TypeError, ValueError):
            return None
        if not normalized_telegram_id:
            return None
        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .where(StaffUser.status == StaffUserService.STATUS_ACTIVE)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                TenantMembership.tenant_id == tenant_scope.tenant_id,
                TenantMembership.status == "active",
            )
        )
        return result.scalars().first()

    @classmethod
    async def list_my_tasks(
        cls,
        session: AsyncSession,
        telegram_id: int | str | None,
        *,
        limit: int = 10,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: list[str] | None = None,
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]]:
        staff = await cls._staff_by_telegram_id(
            session,
            telegram_id,
            tenant_scope=tenant_scope,
        )
        if not staff or not staff.legacy_installer_id:
            return []

        return await cls.list_installer_tasks(
            session,
            int(staff.legacy_installer_id),
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            statuses=statuses,
            tenant_scope=tenant_scope,
        )

    @classmethod
    async def list_installer_tasks(
        cls,
        session: AsyncSession,
        installer_id: int,
        *,
        limit: int = 10,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: list[str] | None = None,
        reference_time: datetime | None = None,
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 10), 20))

        current_time = reference_time or datetime.now()
        range_start = cls._normalize_filter_datetime(
            date_from
        ) or current_time - timedelta(days=1)
        range_end = cls._normalize_filter_datetime(
            date_to
        ) or current_time + timedelta(days=30)
        requested_statuses = {str(value) for value in statuses or []}
        stage_statuses = requested_statuses.intersection(
            status.value for status in OrderStageStatus
        )
        order_statuses = requested_statuses.intersection(
            status.value for status in OrderStatus
        )

        active_stage_filters = [
            OrderWorkStage.installer_id == installer_id,
            Order.status.in_(list(cls.ACTIVE_ORDER_STATUSES)),
            OrderWorkStage.start_time.is_not(None),
            OrderWorkStage.start_time >= range_start,
            OrderWorkStage.start_time <= range_end,
            tenant_or_fully_legacy_scope_clause(Order, tenant_scope),
            TenantEntityAccessService.order_customer_clause(tenant_scope),
        ]
        if requested_statuses:
            active_stage_filters.append(OrderWorkStage.status.in_(stage_statuses))
        else:
            active_stage_filters.extend(
                [
                    OrderWorkStage.status != OrderStageStatus.COMPLETED,
                    OrderWorkStage.status != OrderStageStatus.CANCELED,
                ]
            )

        stage_result = await session.execute(
            select(OrderWorkStage)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(*active_stage_filters)
            .options(
                selectinload(OrderWorkStage.order).selectinload(Order.customer),
            )
            .order_by(OrderWorkStage.start_time.asc().nullslast(), OrderWorkStage.id.asc())
            .limit(safe_limit)
        )
        tasks = [cls._map_stage(stage) for stage in stage_result.scalars().all()]

        active_stage_order_ids = (
            select(OrderWorkStage.order_id)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(*active_stage_filters)
        )

        order_query = (
            select(Order)
            .join(OrderInstaller, OrderInstaller.order_id == Order.id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(OrderInstaller.installer_id == installer_id)
            .where(tenant_or_fully_legacy_scope_clause(Order, tenant_scope))
            .where(TenantEntityAccessService.order_customer_clause(tenant_scope))
            .where(Order.status.in_(list(cls.ACTIVE_ORDER_STATUSES)))
            .where(Order.installation_date.is_not(None))
            .where(
                (Order.installation_date >= range_start)
                & (Order.installation_date <= range_end)
            )
            .where(Order.id.notin_(active_stage_order_ids))
            .options(selectinload(Order.customer))
            .order_by(Order.installation_date.asc().nullslast(), Order.id.asc())
            .limit(safe_limit)
        )
        if requested_statuses:
            order_query = order_query.where(Order.status.in_(order_statuses))
        order_result = await session.execute(order_query)
        tasks.extend(cls._map_order(order) for order in order_result.scalars().all())
        tasks.sort(
            key=lambda task: (
                task["start_time"],
                0 if task["kind"] == "stage" else 1,
                task["id"],
            )
        )
        return tasks[:safe_limit]

    @staticmethod
    def _normalize_filter_datetime(value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is None:
            return value
        try:
            local_timezone = ZoneInfo(settings.BOT_TASK_TIMEZONE)
        except ZoneInfoNotFoundError:
            local_timezone = ZoneInfo("Europe/Minsk")
        return value.astimezone(local_timezone).replace(tzinfo=None)

    @staticmethod
    def _manager_url(order_id: int) -> str:
        base_url = str(
            settings.MANAGER_BASE_URL or "https://api.mvn.by/manager"
        ).rstrip("/")
        return f"{base_url}/orders/kanban?{urlencode({'orderId': order_id})}"

    @staticmethod
    def _customer_phone(order: Order) -> str | None:
        customer = getattr(order, "customer", None)
        return getattr(customer, "phone", None) if customer else None

    @staticmethod
    def _customer_name(order: Order) -> str:
        customer = getattr(order, "customer", None)
        return getattr(customer, "name", None) or "Клиент"

    @classmethod
    def _map_stage(cls, stage: OrderWorkStage) -> dict[str, Any]:
        order = stage.order
        return {
            "kind": "stage",
            "id": int(stage.id or 0),
            "order_id": int(stage.order_id),
            "stage_id": int(stage.id or 0),
            "title": stage.name,
            "status": (
                stage.status.value
                if hasattr(stage.status, "value")
                else str(stage.status)
            ),
            "start_time": stage.start_time,
            "address": order.delivery_address if order else None,
            "customer_name": cls._customer_name(order) if order else "Клиент",
            "customer_phone": cls._customer_phone(order) if order else None,
            "comment": stage.manager_comment,
            "manager_url": cls._manager_url(int(stage.order_id)),
        }

    @classmethod
    def _map_order(cls, order: Order) -> dict[str, Any]:
        return {
            "kind": "order",
            "id": int(order.id or 0),
            "order_id": int(order.id or 0),
            "stage_id": None,
            "title": order.title or "Монтаж",
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "start_time": order.installation_date,
            "address": order.delivery_address,
            "customer_name": cls._customer_name(order),
            "customer_phone": cls._customer_phone(order),
            "comment": order.comment,
            "manager_url": cls._manager_url(int(order.id or 0)),
        }
