from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Awaitable, Callable, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.tenancy import TenantScope
from services.analytics_connection_service import AnalyticsConnectionService
from services.analytics_google_providers import (
    GoogleSearchConsoleProvider,
    access_token as google_access_token,
)
from services.analytics_provider_types import SearchQueryRow
from services.analytics_yandex_providers import YandexWebmasterProvider


SearchDemandStatus = Literal["unconfigured", "fresh", "stale", "error"]


@dataclass(frozen=True)
class SearchDemandProviderState:
    provider: str
    status: SearchDemandStatus
    message: str | None = None


@dataclass(frozen=True)
class SearchDemandQuery:
    provider: str
    query: str
    clicks: float
    impressions: float
    ctr: float
    avg_position: float | None


@dataclass(frozen=True)
class SearchDemandSnapshot:
    status: SearchDemandStatus
    queries: tuple[SearchDemandQuery, ...] = ()
    providers: tuple[SearchDemandProviderState, ...] = ()
    updated_at: datetime | None = None
    message: str | None = None


@dataclass(frozen=True)
class _CacheEntry:
    stored_at: float
    snapshot: SearchDemandSnapshot


class SearchDemandCache:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._entries: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[SearchDemandSnapshot]],
    ) -> SearchDemandSnapshot:
        cached = self._entries.get(key)
        if cached and monotonic() - cached.stored_at <= self._ttl_seconds:
            return cached.snapshot
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._entries.get(key)
            if cached and monotonic() - cached.stored_at <= self._ttl_seconds:
                return cached.snapshot
            try:
                snapshot = await fetch()
            except Exception:
                if cached:
                    return replace(
                        cached.snapshot,
                        status="stale",
                        message="Показаны последние сохранённые поисковые запросы.",
                    )
                return SearchDemandSnapshot(
                    status="error",
                    message="Поисковая аналитика временно недоступна.",
                )
            if snapshot.status == "error" and cached:
                return replace(
                    cached.snapshot,
                    status="stale",
                    message="Показаны последние сохранённые поисковые запросы.",
                )
            self._entries[key] = _CacheEntry(monotonic(), snapshot)
            return snapshot


class IntegratedSearchDemandProvider:
    def __init__(self, *, cache: SearchDemandCache | None = None) -> None:
        self._cache = cache or _PROCESS_CACHE

    async def get_snapshot(
        self,
        *,
        session: AsyncSession,
        tenant_scope: TenantScope,
        start: date,
        end_exclusive: date,
    ) -> SearchDemandSnapshot:
        connections = await AnalyticsConnectionService.get_runtime_connections(
            session,
            tenant_scope=tenant_scope,
        )
        relevant = {
            provider: connection
            for provider, connection in connections.items()
            if provider in {"yandex_webmaster", "google_search_console"}
        }
        fingerprints = ":".join(
            f"{provider}={connection.fingerprint}"
            for provider, connection in sorted(relevant.items())
        )
        key = (
            f"search:{tenant_scope.tenant_id}:{tenant_scope.storefront_id}:"
            f"{fingerprints}:{start.isoformat()}:{end_exclusive.isoformat()}"
        )
        return await self._cache.get_or_fetch(
            key,
            lambda: self._fetch(
                session=session,
                tenant_scope=tenant_scope,
                connections=relevant,
                start=start,
                end_exclusive=end_exclusive,
            ),
        )

    async def _fetch(
        self,
        *,
        session: AsyncSession,
        tenant_scope: TenantScope,
        connections,
        start: date,
        end_exclusive: date,
    ) -> SearchDemandSnapshot:
        queries: list[SearchDemandQuery] = []
        provider_states: list[SearchDemandProviderState] = []

        webmaster = connections.get("yandex_webmaster")
        if webmaster is None:
            provider_states.append(
                SearchDemandProviderState("yandex_webmaster", "unconfigured")
            )
        else:
            try:
                snapshot = await asyncio.wait_for(
                    YandexWebmasterProvider().fetch(
                        str(webmaster.credentials.get("oauth_token") or ""),
                        webmaster.public_config,
                        limit=100,
                        period_start=start,
                        period_end=end_exclusive - timedelta(days=1),
                    ),
                    timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
                )
                queries.extend(_queries("yandex_webmaster", snapshot.rows))
                provider_states.append(SearchDemandProviderState("yandex_webmaster", "fresh"))
            except Exception:
                provider_states.append(
                    SearchDemandProviderState(
                        "yandex_webmaster",
                        "error",
                        "Яндекс Вебмастер временно недоступен.",
                    )
                )

        search_console = connections.get("google_search_console")
        if search_console is None:
            provider_states.append(
                SearchDemandProviderState("google_search_console", "unconfigured")
            )
        else:
            original = dict(search_console.credentials)
            try:
                token = await google_access_token(search_console.credentials)
                snapshot = await asyncio.wait_for(
                    GoogleSearchConsoleProvider().fetch(
                        token,
                        search_console.public_config,
                        start,
                        end_exclusive - timedelta(days=1),
                        limit=100,
                    ),
                    timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
                )
                queries.extend(_queries("google_search_console", snapshot.rows))
                provider_states.append(
                    SearchDemandProviderState("google_search_console", "fresh")
                )
                if search_console.credentials != original:
                    await AnalyticsConnectionService.persist_refreshed_credentials(
                        session,
                        tenant_scope=tenant_scope,
                        provider="google_search_console",
                        credentials=search_console.credentials,
                    )
            except Exception:
                provider_states.append(
                    SearchDemandProviderState(
                        "google_search_console",
                        "error",
                        "Google Search Console временно недоступен.",
                    )
                )

        queries.sort(key=lambda row: (row.clicks, row.impressions), reverse=True)
        statuses = {item.status for item in provider_states}
        status: SearchDemandStatus
        if "fresh" in statuses:
            status = "fresh"
        elif "error" in statuses:
            status = "error"
        else:
            status = "unconfigured"
        return SearchDemandSnapshot(
            status=status,
            queries=tuple(queries[:100]),
            providers=tuple(provider_states),
            updated_at=datetime.now().astimezone() if status == "fresh" else None,
            message=(
                "Часть редких запросов поисковые системы могут скрывать; свежие данные появляются с задержкой."
                if status == "fresh"
                else None
            ),
        )


def _queries(provider: str, rows: tuple[SearchQueryRow, ...]) -> list[SearchDemandQuery]:
    return [
        SearchDemandQuery(
            provider=provider,
            query=row.query,
            clicks=row.clicks,
            impressions=row.impressions,
            ctr=row.ctr,
            avg_position=row.position,
        )
        for row in rows
        if row.query.strip()
    ]


_PROCESS_CACHE = SearchDemandCache(settings.ANALYTICS_PROVIDER_CACHE_TTL_SECONDS)
