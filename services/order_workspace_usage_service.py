from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from crud.order_workspace_usage import increment_daily_usage, list_daily_usage, prune_daily_usage
from models.tenancy import TenantScope
from schemas_order_usage import OrderUsageBatch, OrderUsageDailyItem, OrderUsageReport

USAGE_TIMEZONE = ZoneInfo("Europe/Minsk")
USAGE_RETENTION_DAYS = 90


class OrderWorkspaceUsageService:
    @staticmethod
    async def record(session: AsyncSession, scope: TenantScope, payload: OrderUsageBatch) -> int:
        today = datetime.now(USAGE_TIMEZONE).date()
        counts = Counter(
            (event.metric, event.workflow, event.party_kind, event.viewport)
            for event in payload.events
        )
        rows = [
            dict(
                tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, day=today,
                layout_version=payload.layout_version, metric=metric, workflow=workflow,
                party_kind=party, viewport=viewport, count=count,
            )
            for (metric, workflow, party, viewport), count in sorted(counts.items())
        ]
        await increment_daily_usage(session, rows)
        await prune_daily_usage(session, scope, today - timedelta(days=USAGE_RETENTION_DAYS - 1))
        await session.commit()
        return len(payload.events)

    @staticmethod
    async def report(
        session: AsyncSession, scope: TenantScope, *, days: int,
        workflow: str | None = None, party_kind: str | None = None, viewport: str | None = None,
    ) -> OrderUsageReport:
        through = datetime.now(USAGE_TIMEZONE).date()
        since = through - timedelta(days=days - 1)
        rows = await list_daily_usage(
            session, scope, since=since, through=through,
            workflow=workflow, party_kind=party_kind, viewport=viewport,
        )
        return OrderUsageReport(days=days, since=since, through=through, items=[
            OrderUsageDailyItem(
                day=row.day, metric=row.metric, workflow=row.workflow,
                party_kind=row.party_kind, viewport=row.viewport, count=row.count,
            ) for row in rows
        ])
