"""Scheduler-owned refresh. GETs never enqueue work; each source owns a session."""
import asyncio
from datetime import datetime, timezone

from core.database import async_session_maker
from core.logger import logger
from crud import dashboard_analytics as store
from services.dashboard_analytics_snapshots import configurations, key_values, ttl, utc, SEARCH_PROVIDERS
from services.dashboard_overview_service import current_month_window


class DashboardAnalyticsWorker:
    def __init__(self, *, session_factory=None, fetch_source=None, concurrency=2, batch_limit=24, clock=None):
        from services.dashboard_analytics_sources import fetch_source as default_fetch
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.session_factory = session_factory or async_session_maker
        self.fetch_source = fetch_source or default_fetch
        self.concurrency = max(1, min(concurrency, 4))
        self.batch_limit = max(1, min(batch_limit, 100))

    async def run_once(self, *, now=None):
        now = now or self.clock()
        window = current_month_window(now)
        pending = []
        async with self.session_factory() as session:
            scopes = await store.active_scopes(session)
            for scope in scopes:
                for config in await configurations(session, scope):
                    periods = [(window.current_start.date(), window.current_end.date())]
                    if config.provider not in SEARCH_PROVIDERS:
                        periods.append((window.previous_start.date(), window.previous_end.date()))
                    for start, end in periods:
                        pending.append((scope, config, key_values(scope, config, start, end)))
            known = await store.exact_rows(session, [item[2]["key"] for item in pending])
        def due(item):
            row = known.get(item[2]["key"])
            return row is None or ((row.next_retry_at is None or utc(row.next_retry_at) <= utc(now))
                                   and (row.lease_until is None or utc(row.lease_until) <= utc(now)))
        pending = [item for item in pending if due(item)]
        # Oldest attempts first, so a permanently failing source cannot starve others.
        pending.sort(key=lambda item: utc(known[item[2]["key"]].last_attempt_at).timestamp()
                     if item[2]["key"] in known and known[item[2]["key"]].last_attempt_at else 0)
        semaphore = asyncio.Semaphore(self.concurrency)
        async def refresh(item):
            async with semaphore:
                return await self._refresh(*item, now=self.clock())
        results = await asyncio.gather(*(refresh(item) for item in pending[:self.batch_limit]), return_exceptions=True)
        # Await every owned task even if one database operation fails. Otherwise
        # gather would return early and leave source tasks outside loop cancellation.
        for result in results:
            if isinstance(result, BaseException):
                logger.error("DASHBOARD_SNAPSHOT_WORKER_FAILED error_type=%s", type(result).__name__)
        return sum(result for result in results if isinstance(result, int))

    async def _refresh(self, scope, config, values, *, now):
        async with self.session_factory() as session:
            token = await store.claim(session, values=values, now=now)
            if not token:
                return 0
            try:
                # Re-check configuration after discovery/claim, before any provider I/O.
                current = await configurations(session, scope)
                if config not in current:
                    await store.finish(session, key=values["key"], token=token, now=now, error_code="source_changed")
                    return 0
                payload = await asyncio.wait_for(self.fetch_source(session, scope, config.provider,
                    values["period_start"], values["period_end"]), timeout=35)
                current = await configurations(session, scope)
                if config not in current:
                    await session.rollback()
                    await store.finish(session, key=values["key"], token=token, now=self.clock(), error_code="source_changed")
                    return 0
                await store.finish(session, key=values["key"], token=token, now=self.clock(),
                                   payload=payload, ttl_seconds=ttl(config.provider))
            except asyncio.CancelledError:
                # Lease expires after worker loss; no request task survives scheduler cancellation.
                raise
            except Exception as exc:
                await session.rollback()
                code = "timeout" if isinstance(exc, TimeoutError) else "provider_unavailable"
                await store.finish(session, key=values["key"], token=token, now=self.clock(), error_code=code)
                logger.warning("DASHBOARD_SNAPSHOT_FAILED provider=%s tenant_id=%s storefront_id=%s code=%s",
                               config.provider, scope.tenant_id, scope.storefront_id, code)
        return 1
