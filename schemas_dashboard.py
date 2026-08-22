from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardPeriodRange(BaseModel):
    start: datetime
    end: datetime


class DashboardPeriod(BaseModel):
    kind: Literal["current_month"] = "current_month"
    timezone: Literal["Europe/Minsk"] = "Europe/Minsk"
    current: DashboardPeriodRange
    previous: DashboardPeriodRange


class DashboardKpi(BaseModel):
    label: str
    unit: Literal["byn", "count"]
    current: int | float
    previous: int | float | None = Field(
        description="Previous-period value; null for current-state snapshots without historical state.",
    )
    delta_pct: float | None = Field(
        default=None,
        description="Percentage change; null when the previous value is zero.",
    )
    trend: Literal["up", "down", "flat", "unavailable"]


class DashboardKpis(BaseModel):
    revenue: DashboardKpi = Field(
        description="Actual BYN Payment.amount grouped by Payment.date.",
    )
    new_leads: DashboardKpi = Field(
        description="Canonical Lead rows grouped by Lead.created_at; legacy order inbox rows are not double-counted.",
    )
    sales: DashboardKpi = Field(
        description="Orders closed as won, grouped strictly by Order.closed_at.",
    )
    installations: DashboardKpi = Field(
        description="Completed work stages named 'Монтаж' (trimmed, case-insensitive), grouped by end_time and falling back to the parent order updated_at proxy.",
    )
    active_tasks: DashboardKpi = Field(
        description="Current active lead/order touchpoint backlog; historical snapshot is unavailable.",
    )
    receivables: DashboardKpi = Field(
        description="Current positive balance_due snapshot across all BYN negotiation/execution orders; historical snapshot is unavailable.",
    )


class DashboardSalesSeriesPoint(BaseModel):
    date: date
    revenue: float
    sales: int


class DashboardFunnelStage(BaseModel):
    """Monthly stage events, not a cohort funnel.

    Measurements require a recorded measurement_result and use measurement_date;
    proposals use proposal_sent_at; sales use closed_at on closed/won orders;
    installations use completed stages named "Монтаж" and the timestamp policy
    documented by the KPI.
    Cycle time is measured from Order.created_at to the stage event.
    """

    stage: Literal[
        "visitors",
        "leads",
        "measurements",
        "proposals",
        "sales",
        "installations",
    ]
    label: str
    current: int | None = None
    previous: int | None = None
    conversion_from_previous_pct: float | None = None
    avg_cycle_days: float | None = Field(
        default=None,
        description="Average days from Order.created_at to this stage event.",
    )


class DashboardMarketingSource(BaseModel):
    name: str
    visits: int
    share_pct: float


class DashboardMarketingProvider(BaseModel):
    provider: Literal[
        "yandex_metrika",
        "yandex_direct",
        "google_analytics",
        "google_ads",
    ]
    status: Literal["unconfigured", "fresh", "stale", "error"]
    visits: int | None = None
    ad_spend: float | None = None
    clicks: int | None = None
    impressions: int | None = None
    ctr: float | None = None
    platform_conversions: float | None = None
    currency: str | None = None
    message: str | None = None


class DashboardMarketing(BaseModel):
    status: Literal["unconfigured", "fresh", "stale", "error"]
    provider: Literal["integrated", "yandex_metrika"] = "integrated"
    visits: int | None = None
    sources: list[DashboardMarketingSource] = Field(default_factory=list)
    ad_spend: float | None = None
    clicks: int | None = None
    impressions: int | None = None
    ctr: float | None = None
    leads: int | None = None
    cost_per_lead: float | None = None
    customer_acquisition_cost: float | None = None
    platform_conversions: float | None = None
    currency: str | None = None
    providers: list[DashboardMarketingProvider] = Field(default_factory=list)
    updated_at: datetime | None = None
    message: str | None = None


class DashboardSearchQuery(BaseModel):
    provider: Literal["yandex_webmaster", "google_search_console"]
    query: str
    clicks: float
    impressions: float
    ctr: float
    avg_position: float | None = None


class DashboardSearchDemandProvider(BaseModel):
    provider: Literal["yandex_webmaster", "google_search_console"]
    status: Literal["unconfigured", "fresh", "stale", "error"]
    message: str | None = None


class DashboardSearchDemand(BaseModel):
    status: Literal["unconfigured", "fresh", "stale", "error"]
    queries: list[DashboardSearchQuery] = Field(default_factory=list)
    providers: list[DashboardSearchDemandProvider] = Field(default_factory=list)
    updated_at: datetime | None = None
    message: str | None = None


class DashboardOverviewResponse(BaseModel):
    generated_at: datetime
    period: DashboardPeriod
    kpis: DashboardKpis
    sales_series: list[DashboardSalesSeriesPoint]
    funnel: list[DashboardFunnelStage]
    marketing: DashboardMarketing
    search_demand: DashboardSearchDemand
