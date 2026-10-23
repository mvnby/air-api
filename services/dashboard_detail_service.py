"""Bounded, storefront-scoped records behind dashboard KPIs."""

from datetime import datetime, timedelta

from sqlalchemy import Float, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer import Lead
from models.order import Order, OrderWorkStage, Payment
from models.tenancy import TenantScope
from schemas_dashboard import DashboardDetailItem, DashboardDetailResponse, DashboardMetric, DashboardPeriodRange
from services.dashboard_kpi_queries import (
    installation_completed_at, installation_conditions, lead_conditions,
    lead_touchpoint_conditions, order_touchpoint_conditions, receivable_conditions,
    revenue_conditions, sales_conditions,
)
from services.dashboard_overview_service import DASHBOARD_TIMEZONE


def _records(metric, scope, bounds):
    def order_rows(record_id, occurred_at, value=literal(1)):
        return select(
            record_id.label("record_id"), literal("order").label("entity_type"),
            Order.id.label("entity_id"), func.coalesce(Order.title, "").label("title"),
            occurred_at.label("occurred_at"), cast(value, Float).label("value"),
        )

    def lead_rows(occurred_at):
        return select(
            Lead.id.label("record_id"), literal("lead").label("entity_type"),
            Lead.id.label("entity_id"),
            func.substr(func.coalesce(Lead.company_name, Lead.name, Lead.request_text, ""), 1, 200).label("title"),
            occurred_at.label("occurred_at"), cast(literal(1), Float).label("value"),
        )

    if metric == "revenue":
        return order_rows(Payment.id, Payment.date, Payment.amount).select_from(Payment).join(
            Order, Order.id == Payment.order_id,
        ).where(*revenue_conditions(scope, bounds))
    if metric == "sales":
        return order_rows(Order.id, Order.closed_at).where(*sales_conditions(scope, bounds))
    if metric == "installations":
        return order_rows(OrderWorkStage.id, installation_completed_at()).select_from(OrderWorkStage).join(
            Order, Order.id == OrderWorkStage.order_id,
        ).where(*installation_conditions(scope, bounds))
    if metric == "new_leads":
        return lead_rows(Lead.created_at).where(*lead_conditions(scope, bounds))
    if metric == "receivables":
        return order_rows(Order.id, literal(None), Order.balance_due).where(*receivable_conditions(scope))
    return union_all(
        order_rows(Order.id, Order.next_followup_date).where(*order_touchpoint_conditions(scope)),
        lead_rows(Lead.next_followup_date).where(*lead_touchpoint_conditions(scope)),
    )


class DashboardDetailService:
    @staticmethod
    async def list(
        session: AsyncSession, *, tenant_scope: TenantScope, metric: DashboardMetric,
        start: datetime, end: datetime, limit: int = 50, offset: int = 0,
    ) -> DashboardDetailResponse:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Укажите часовой пояс периода")
        if not start < end or end - start > timedelta(days=32):
            raise ValueError("Период должен быть от одного момента до 32 дней")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Некорректная страница")
        bounds = tuple(value.astimezone(DASHBOARD_TIMEZONE).replace(tzinfo=None) for value in (start, end))
        rows = _records(metric, tenant_scope, bounds).subquery()
        total, value = (await session.execute(
            select(func.count(), func.coalesce(func.sum(rows.c.value), 0)).select_from(rows)
        )).one()
        money = metric in {"revenue", "receivables"}
        ordering = rows.c.occurred_at.asc().nullslast() if metric == "active_tasks" else rows.c.occurred_at.desc().nullslast()
        records = (await session.execute(
            select(rows).order_by(ordering, rows.c.entity_type, rows.c.record_id.desc()).limit(limit).offset(offset)
        )).mappings().all()
        return DashboardDetailResponse(
            metric=metric, total=total, value=round(float(value), 2),
            unit="byn" if money else "count", limit=limit, offset=offset,
            generated_at=datetime.now(DASHBOARD_TIMEZONE),
            period=None if metric in {"receivables", "active_tasks"} else DashboardPeriodRange(start=start, end=end),
            items=[DashboardDetailItem(
                record_id=row["record_id"], entity_type=row["entity_type"], entity_id=row["entity_id"],
                title=row["title"],
                occurred_at=row["occurred_at"].replace(tzinfo=DASHBOARD_TIMEZONE) if row["occurred_at"] else None,
                amount=float(row["value"]) if money else None,
            ) for row in records],
        )
