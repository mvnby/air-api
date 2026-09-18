from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from crud.catalog_workspace_usage import increment_daily_usage, list_daily_usage, prune_daily_usage
from schemas_catalog_usage import CatalogUsageBatch, CatalogUsageDailyItem, CatalogUsageReport


USAGE_TIMEZONE = ZoneInfo("Europe/Minsk")
USAGE_RETENTION_DAYS = 90


class CatalogWorkspaceUsageService:
    @staticmethod
    async def record(session: AsyncSession, payload: CatalogUsageBatch) -> int:
        today = datetime.now(USAGE_TIMEZONE).date()
        counts = Counter(
            (event.device, event.action, event.outcome, event.duration_bucket)
            for event in payload.events
        )
        await increment_daily_usage(session, [
            dict(
                day=today, layout_version=payload.layout_version, device=device,
                action=action, outcome=outcome, duration_bucket=duration_bucket, count=count,
            )
            for (device, action, outcome, duration_bucket), count in sorted(counts.items())
        ])
        await prune_daily_usage(session, before=today - timedelta(days=USAGE_RETENTION_DAYS - 1))
        await session.commit()
        return len(payload.events)

    @staticmethod
    async def report(
        session: AsyncSession, *, days: int, layout_version: str | None = None,
        device: str | None = None, action: str | None = None, outcome: str | None = None,
    ) -> CatalogUsageReport:
        through = datetime.now(USAGE_TIMEZONE).date()
        since = through - timedelta(days=days - 1)
        rows = await list_daily_usage(
            session, since=since, through=through, layout_version=layout_version,
            device=device, action=action, outcome=outcome,
        )
        return CatalogUsageReport(days=days, since=since, through=through, items=[
            CatalogUsageDailyItem(
                day=row.day, layout_version=row.layout_version, device=row.device,
                action=row.action, outcome=row.outcome,
                duration_bucket=row.duration_bucket, count=row.count,
            ) for row in rows
        ])
