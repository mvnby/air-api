from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.common import ClosingResult, LeadStatus, OrderStageStatus, OrderStatus, PaymentCurrency
from models.customer import Lead
from models.order import Order, OrderWorkStage, Payment
from models.tenancy import TenantScope
from schemas_dashboard import (
    DashboardFunnelStage,
    DashboardKpi,
    DashboardKpis,
    DashboardMarketing,
    DashboardMarketingProvider,
    DashboardMarketingSource,
    DashboardOverviewResponse,
    DashboardPeriod,
    DashboardPeriodRange,
    DashboardSearchDemand,
    DashboardSearchDemandProvider,
    DashboardSearchQuery,
    DashboardSalesSeriesPoint,
)
from services.dashboard_marketing import IntegratedMarketingProvider, MarketingSnapshot
from services.dashboard_search_demand import (
    IntegratedSearchDemandProvider,
    SearchDemandSnapshot,
)
from services.order_financial_eligibility import collectible_order_clause
from services.tenant_scope_service import storefront_scope_clause


DASHBOARD_TIMEZONE = ZoneInfo("Europe/Minsk")


@dataclass(frozen=True)
class DashboardPeriodWindow:
    generated_at: datetime
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime

    @property
    def current_query_bounds(self) -> tuple[datetime, datetime]:
        return (_naive(self.current_start), _naive(self.current_end))

    @property
    def previous_query_bounds(self) -> tuple[datetime, datetime]:
        return (_naive(self.previous_start), _naive(self.previous_end))


def current_month_window(now: datetime | None = None) -> DashboardPeriodWindow:
    generated_at = now or datetime.now(DASHBOARD_TIMEZONE)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=DASHBOARD_TIMEZONE)
    else:
        generated_at = generated_at.astimezone(DASHBOARD_TIMEZONE)
    current_start = datetime.combine(
        generated_at.date().replace(day=1),
        time.min,
        tzinfo=DASHBOARD_TIMEZONE,
    )
    current_end = _next_month(current_start)
    previous_start = _previous_month(current_start)
    return DashboardPeriodWindow(
        generated_at=generated_at,
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=current_start,
    )


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _previous_month(value: datetime) -> datetime:
    if value.month == 1:
        return value.replace(year=value.year - 1, month=12)
    return value.replace(month=value.month - 1)


def _naive(value: datetime) -> datetime:
    return value.astimezone(DASHBOARD_TIMEZONE).replace(tzinfo=None)


def delta_and_trend(
    current: float,
    previous: float | None,
) -> tuple[float | None, str]:
    if previous is None:
        return None, "unavailable"
    if current > previous:
        trend = "up"
    elif current < previous:
        trend = "down"
    else:
        trend = "flat"
    if previous == 0:
        return None, trend
    return round((current - previous) * 100 / previous, 2), trend


def _kpi(
    *,
    label: str,
    unit: str,
    current: float | int,
    previous: float | int | None,
) -> DashboardKpi:
    delta_pct, trend = delta_and_trend(
        float(current),
        float(previous) if previous is not None else None,
    )
    return DashboardKpi(
        label=label,
        unit=unit,
        current=current,
        previous=previous,
        delta_pct=delta_pct,
        trend=trend,
    )


class DashboardOverviewService:
    """Build the manager overview from exact server-resolved storefront data.

    Canonical leads are rows in ``Lead``. Order rows in the legacy inbox are not
    added, preventing one qualified lead from being counted twice. Installations
    use completed stages named ``Монтаж`` in ``sales_installation`` orders;
    ``end_time`` is the best stage timestamp currently available and
    ``Order.updated_at`` is an explicit proxy only when the stage has no end
    time. Touchpoints and receivables are current-state snapshots, so their
    previous values are intentionally unavailable.
    """

    def __init__(
        self,
        *,
        marketing_provider: IntegratedMarketingProvider | None = None,
        search_demand_provider: IntegratedSearchDemandProvider | None = None,
    ) -> None:
        self._marketing_provider = marketing_provider or IntegratedMarketingProvider()
        self._search_demand_provider = search_demand_provider or IntegratedSearchDemandProvider()

    async def get_overview(
        self,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        now: datetime | None = None,
    ) -> DashboardOverviewResponse:
        period = current_month_window(now)
        current_bounds = period.current_query_bounds
        previous_bounds = period.previous_query_bounds

        revenue_current, revenue_by_day = await self._revenue(
            session, tenant_scope=tenant_scope, bounds=current_bounds, by_day=True
        )
        revenue_previous, _ = await self._revenue(
            session, tenant_scope=tenant_scope, bounds=previous_bounds, by_day=False
        )
        leads_current = await self._lead_count(session, tenant_scope, current_bounds)
        leads_previous = await self._lead_count(session, tenant_scope, previous_bounds)
        sales_current, sales_by_day, sales_cycle = await self._sales(
            session, tenant_scope, current_bounds, by_day=True
        )
        sales_previous, _, _ = await self._sales(
            session, tenant_scope, previous_bounds, by_day=False
        )
        installations_current, installation_cycle = await self._installations(
            session, tenant_scope, current_bounds
        )
        installations_previous, _ = await self._installations(
            session, tenant_scope, previous_bounds
        )
        tasks_current = await self._touchpoints(session, tenant_scope)
        receivables_current = await self._receivables(session, tenant_scope)
        measurements_current, measurement_cycle = await self._measurements(
            session, tenant_scope, current_bounds
        )
        measurements_previous, _ = await self._measurements(
            session, tenant_scope, previous_bounds
        )
        proposals_current, proposal_cycle = await self._proposals(
            session, tenant_scope, current_bounds
        )
        proposals_previous, _ = await self._proposals(
            session, tenant_scope, previous_bounds
        )
        acquired_customers_current = await self._acquired_customers(
            session,
            tenant_scope,
            current_bounds,
        )

        # AsyncSession is intentionally not shared across concurrent tasks.
        # Each provider call resolves the exact storefront connection first.
        current_marketing = await self._safe_marketing(
            session,
            tenant_scope,
            start=period.current_start.date(),
            end_exclusive=min(
                period.current_end.date(),
                period.generated_at.date() + timedelta(days=1),
            ),
        )
        previous_marketing = await self._safe_marketing(
            session,
            tenant_scope,
            start=period.previous_start.date(),
            end_exclusive=period.previous_end.date(),
        )
        current_search_demand = await self._safe_search_demand(
            session,
            tenant_scope,
            start=period.current_start.date(),
            end_exclusive=min(
                period.current_end.date(),
                period.generated_at.date() + timedelta(days=1),
            ),
        )

        series = _build_daily_series(
            start=period.current_start.date(),
            end_exclusive=min(period.current_end.date(), period.generated_at.date() + timedelta(days=1)),
            revenue_by_day=revenue_by_day,
            sales_by_day=sales_by_day,
        )
        funnel_counts = [
            ("visitors", "Посетители", current_marketing.visits, previous_marketing.visits, None),
            ("leads", "Лиды", leads_current, leads_previous, None),
            ("measurements", "Замеры", measurements_current, measurements_previous, measurement_cycle),
            ("proposals", "Предложения", proposals_current, proposals_previous, proposal_cycle),
            ("sales", "Продажи", sales_current, sales_previous, sales_cycle),
            ("installations", "Монтажи", installations_current, installations_previous, installation_cycle),
        ]

        return DashboardOverviewResponse(
            generated_at=period.generated_at,
            period=DashboardPeriod(
                current=DashboardPeriodRange(start=period.current_start, end=period.current_end),
                previous=DashboardPeriodRange(start=period.previous_start, end=period.previous_end),
            ),
            kpis=DashboardKpis(
                revenue=_kpi(
                    label="Оплаты за месяц",
                    unit="byn",
                    current=revenue_current,
                    previous=revenue_previous,
                ),
                new_leads=_kpi(label="Новые лиды", unit="count", current=leads_current, previous=leads_previous),
                sales=_kpi(label="Продажи", unit="count", current=sales_current, previous=sales_previous),
                installations=_kpi(label="Монтажи", unit="count", current=installations_current, previous=installations_previous),
                active_tasks=_kpi(
                    label="Касания",
                    unit="count",
                    current=tasks_current,
                    previous=None,
                ),
                receivables=_kpi(
                    label="Дебиторка",
                    unit="byn",
                    current=receivables_current,
                    previous=None,
                ),
            ),
            sales_series=series,
            funnel=_build_funnel(funnel_counts),
            marketing=_marketing_schema(
                current_marketing,
                leads=leads_current,
                acquired_customers=acquired_customers_current,
            ),
            search_demand=_search_demand_schema(current_search_demand),
        )

    async def _revenue(self, session, *, tenant_scope, bounds, by_day):
        conditions = (
            storefront_scope_clause(Order, tenant_scope),
            Payment.currency == PaymentCurrency.BYN,
            Payment.date >= bounds[0],
            Payment.date < bounds[1],
        )
        total = await _scalar(
            session,
            select(func.coalesce(func.sum(Payment.amount), 0.0))
            .join(Order, Order.id == Payment.order_id)
            .where(*conditions),
            float,
        )
        daily: dict[date, float] = {}
        if by_day:
            result = await session.execute(
                select(func.date(Payment.date), func.sum(Payment.amount))
                .join(Order, Order.id == Payment.order_id)
                .where(*conditions)
                .group_by(func.date(Payment.date))
            )
            daily = {row[0]: float(row[1] or 0) for row in result.all()}
        return total, daily

    async def _lead_count(self, session, tenant_scope, bounds):
        return await _scalar(
            session,
            select(func.count(Lead.id)).where(
                storefront_scope_clause(Lead, tenant_scope),
                Lead.created_at >= bounds[0],
                Lead.created_at < bounds[1],
            ),
            int,
        )

    async def _sales(self, session, tenant_scope, bounds, *, by_day):
        conditions = (
            storefront_scope_clause(Order, tenant_scope),
            Order.status == OrderStatus.CLOSED,
            Order.closing_result == ClosingResult.WON.value,
            Order.closed_at.is_not(None),
            Order.closed_at >= bounds[0],
            Order.closed_at < bounds[1],
        )
        count = await _scalar(session, select(func.count(Order.id)).where(*conditions), int)
        cycle = await _average_cycle(session, Order.closed_at, conditions)
        daily: dict[date, int] = {}
        if by_day:
            result = await session.execute(
                select(func.date(Order.closed_at), func.count(Order.id))
                .where(*conditions)
                .group_by(func.date(Order.closed_at))
            )
            daily = {row[0]: int(row[1] or 0) for row in result.all()}
        return count, daily, cycle

    async def _acquired_customers(self, session, tenant_scope, bounds):
        return await _scalar(
            session,
            select(func.count(func.distinct(Order.customer_id))).where(
                storefront_scope_clause(Order, tenant_scope),
                Order.customer_id.is_not(None),
                Order.status == OrderStatus.CLOSED,
                Order.closing_result == ClosingResult.WON.value,
                Order.closed_at.is_not(None),
                Order.closed_at >= bounds[0],
                Order.closed_at < bounds[1],
            ),
            int,
        )

    async def _installations(self, session, tenant_scope, bounds):
        completed_at = func.coalesce(OrderWorkStage.end_time, Order.updated_at)
        conditions = (
            storefront_scope_clause(Order, tenant_scope),
            Order.workflow_type == "sales_installation",
            OrderWorkStage.status == OrderStageStatus.COMPLETED,
            func.lower(func.trim(OrderWorkStage.name)) == "монтаж",
            completed_at >= bounds[0],
            completed_at < bounds[1],
        )
        count = await _scalar(
            session,
            select(func.count(OrderWorkStage.id))
            .join(Order, Order.id == OrderWorkStage.order_id)
            .where(*conditions),
            int,
        )
        cycle = await _average_cycle(
            session,
            completed_at,
            conditions,
            from_entity=OrderWorkStage,
        )
        return count, cycle

    async def _touchpoints(self, session, tenant_scope):
        order_count = await _scalar(
            session,
            select(func.count(Order.id)).where(
                storefront_scope_clause(Order, tenant_scope),
                Order.status != OrderStatus.CLOSED,
                Order.next_followup_date.is_not(None),
            ),
            int,
        )
        lead_count = await _scalar(
            session,
            select(func.count(Lead.id)).where(
                storefront_scope_clause(Lead, tenant_scope),
                Lead.status.in_([LeadStatus.new, LeadStatus.contacted]),
                Lead.next_followup_date.is_not(None),
            ),
            int,
        )
        return order_count + lead_count

    async def _receivables(self, session, tenant_scope):
        return await _scalar(
            session,
            select(func.coalesce(func.sum(Order.balance_due), 0.0)).where(
                storefront_scope_clause(Order, tenant_scope),
                collectible_order_clause(),
                Order.balance_due > 0,
                or_(Order.target_currency.is_(None), Order.target_currency == PaymentCurrency.BYN),
            ),
            float,
        )

    async def _measurements(self, session, tenant_scope, bounds):
        conditions = (
            storefront_scope_clause(Order, tenant_scope),
            Order.measurement_result.is_not(None),
            Order.measurement_date.is_not(None),
            Order.measurement_date >= bounds[0],
            Order.measurement_date < bounds[1],
        )
        return (
            await _scalar(session, select(func.count(Order.id)).where(*conditions), int),
            await _average_cycle(session, Order.measurement_date, conditions),
        )

    async def _proposals(self, session, tenant_scope, bounds):
        conditions = (
            storefront_scope_clause(Order, tenant_scope),
            Order.proposal_sent_at.is_not(None),
            Order.proposal_sent_at >= bounds[0],
            Order.proposal_sent_at < bounds[1],
        )
        return (
            await _scalar(session, select(func.count(Order.id)).where(*conditions), int),
            await _average_cycle(session, Order.proposal_sent_at, conditions),
        )

    async def _safe_marketing(self, session, tenant_scope, *, start, end_exclusive):
        try:
            return await self._marketing_provider.get_snapshot(
                session=session,
                tenant_scope=tenant_scope,
                start=start,
                end_exclusive=end_exclusive,
            )
        except Exception:
            return MarketingSnapshot(
                status="error",
                message="Marketing analytics is temporarily unavailable.",
            )

    async def _safe_search_demand(self, session, tenant_scope, *, start, end_exclusive):
        try:
            return await self._search_demand_provider.get_snapshot(
                session=session,
                tenant_scope=tenant_scope,
                start=start,
                end_exclusive=end_exclusive,
            )
        except Exception:
            return SearchDemandSnapshot(
                status="error",
                message="Search analytics is temporarily unavailable.",
            )


async def _scalar(session, statement, cast):
    value = (await session.execute(statement)).scalar()
    return cast(value or 0)


async def _average_cycle(session, stage_time, conditions, *, from_entity=None):
    statement = select(
        func.avg(func.extract("epoch", stage_time - Order.created_at) / 86400.0)
    )
    if from_entity is not None:
        statement = statement.select_from(from_entity).join(
            Order, Order.id == from_entity.order_id
        )
    value = (await session.execute(statement.where(*conditions))).scalar()
    return round(max(0.0, float(value)), 1) if value is not None else None


def _build_daily_series(*, start, end_exclusive, revenue_by_day, sales_by_day):
    result: list[DashboardSalesSeriesPoint] = []
    cursor = start
    while cursor < end_exclusive:
        result.append(
            DashboardSalesSeriesPoint(
                date=cursor,
                revenue=round(float(revenue_by_day.get(cursor, 0.0)), 2),
                sales=int(sales_by_day.get(cursor, 0)),
            )
        )
        cursor += timedelta(days=1)
    return result


def _conversion(current: int | None, previous_stage: int | None) -> float | None:
    if current is None or previous_stage in (None, 0):
        return None
    return round(current * 100 / previous_stage, 2)


def _build_funnel(counts):
    result: list[DashboardFunnelStage] = []
    previous_current: int | None = None
    for stage, label, current, previous, cycle in counts:
        result.append(
            DashboardFunnelStage(
                stage=stage,
                label=label,
                current=current,
                previous=previous,
                conversion_from_previous_pct=_conversion(current, previous_current),
                avg_cycle_days=cycle,
            )
        )
        previous_current = current
    return result


def _marketing_schema(
    snapshot: MarketingSnapshot,
    *,
    leads: int,
    acquired_customers: int,
) -> DashboardMarketing:
    spend = snapshot.ad_spend
    return DashboardMarketing(
        status=snapshot.status,
        visits=snapshot.visits,
        sources=[
            DashboardMarketingSource(
                name=item.name,
                visits=item.visits,
                share_pct=item.share_pct,
            )
            for item in snapshot.sources
        ],
        ad_spend=spend,
        clicks=snapshot.clicks,
        impressions=snapshot.impressions,
        ctr=snapshot.ctr,
        leads=leads,
        cost_per_lead=(round(spend / leads, 2) if spend is not None and leads else None),
        customer_acquisition_cost=(
            round(spend / acquired_customers, 2)
            if spend is not None and acquired_customers
            else None
        ),
        platform_conversions=snapshot.platform_conversions,
        currency=snapshot.currency,
        providers=[
            DashboardMarketingProvider(
                provider=item.provider,
                status=item.status,
                visits=item.visits,
                ad_spend=item.ad_spend,
                clicks=item.clicks,
                impressions=item.impressions,
                ctr=item.ctr,
                platform_conversions=item.platform_conversions,
                currency=item.currency,
                message=item.message,
            )
            for item in snapshot.providers
        ],
        updated_at=snapshot.updated_at,
        message=snapshot.message,
    )


def _search_demand_schema(snapshot: SearchDemandSnapshot) -> DashboardSearchDemand:
    return DashboardSearchDemand(
        status=snapshot.status,
        queries=[
            DashboardSearchQuery(
                provider=item.provider,
                query=item.query,
                clicks=item.clicks,
                impressions=item.impressions,
                ctr=item.ctr,
                avg_position=item.avg_position,
            )
            for item in snapshot.queries
        ],
        providers=[
            DashboardSearchDemandProvider(
                provider=item.provider,
                status=item.status,
                message=item.message,
            )
            for item in snapshot.providers
        ],
        updated_at=snapshot.updated_at,
        message=snapshot.message,
    )
