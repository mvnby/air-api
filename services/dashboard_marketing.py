from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Awaitable, Callable, Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.tenancy import TenantScope
from services.analytics_connection_service import AnalyticsConnectionService


MarketingStatus = Literal["unconfigured", "fresh", "stale", "error"]


@dataclass(frozen=True)
class MarketingSourceSnapshot:
    name: str
    visits: int
    share_pct: float


@dataclass(frozen=True)
class MarketingSnapshot:
    status: MarketingStatus
    visits: int | None = None
    sources: tuple[MarketingSourceSnapshot, ...] = ()
    updated_at: datetime | None = None
    message: str | None = None


@dataclass(frozen=True)
class _CacheEntry:
    stored_at: float
    snapshot: MarketingSnapshot


class MarketingSnapshotCache:
    """Small process-local cache; credentials and raw provider responses are never stored."""

    def __init__(self, *, ttl_seconds: float) -> None:
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._entries: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[MarketingSnapshot]],
    ) -> MarketingSnapshot:
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
                        message="Yandex Metrika is temporarily unavailable; cached data is shown.",
                    )
                return MarketingSnapshot(
                    status="error",
                    message="Yandex Metrika is temporarily unavailable.",
                )
            self._entries[key] = _CacheEntry(
                stored_at=monotonic(),
                snapshot=snapshot,
            )
            return snapshot


def resolve_metrika_counter_id(
    tenant_scope: TenantScope,
    *,
    scoped_counters_json: str,
) -> str | None:
    """Resolve only an exact storefront counter; missing provenance fails closed."""
    try:
        configured = json.loads(scoped_counters_json or "{}")
    except (TypeError, ValueError):
        configured = {}
    if isinstance(configured, dict):
        scoped = str(
            configured.get(
                f"{tenant_scope.tenant_id}:{tenant_scope.storefront_id}",
                "",
            )
        ).strip()
        if scoped.isdigit():
            return scoped
    return None


class YandexMetrikaMarketingProvider:
    API_URL = "https://api-metrika.yandex.net/stat/v1/data"

    def __init__(
        self,
        *,
        oauth_token: str | None = None,
        scoped_counters_json: str | None = None,
        timeout_seconds: float | None = None,
        cache: MarketingSnapshotCache | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._oauth_token = (
            settings.DASHBOARD_METRIKA_OAUTH_TOKEN
            if oauth_token is None
            else oauth_token
        ).strip()
        self._scoped_counters_json = (
            settings.DASHBOARD_METRIKA_STOREFRONT_COUNTERS_JSON
            if scoped_counters_json is None
            else scoped_counters_json
        )
        self._timeout_seconds = (
            settings.DASHBOARD_METRIKA_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._cache = cache or _PROCESS_CACHE
        self._client_factory = client_factory or self._default_client

    def _default_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=max(0.1, self._timeout_seconds),
            trust_env=False,
        )

    async def get_snapshot(
        self,
        *,
        session: AsyncSession | None = None,
        tenant_scope: TenantScope,
        start: date,
        end_exclusive: date,
    ) -> MarketingSnapshot:
        oauth_token = self._oauth_token
        counter_id = resolve_metrika_counter_id(
            tenant_scope,
            scoped_counters_json=self._scoped_counters_json,
        )
        fingerprint = "environment"
        if session is not None:
            stored = await AnalyticsConnectionService.get_metrika_runtime_credentials(
                session,
                tenant_scope=tenant_scope,
            )
            if stored is not None:
                oauth_token = stored.oauth_token
                counter_id = stored.counter_id
                fingerprint = stored.fingerprint
        if not oauth_token or not counter_id:
            return MarketingSnapshot(
                status="unconfigured",
                message="Yandex Metrika is not configured for this storefront.",
            )
        key = (
            f"{tenant_scope.tenant_id}:{tenant_scope.storefront_id}:"
            f"{counter_id}:{fingerprint}:{start.isoformat()}:{end_exclusive.isoformat()}"
        )
        return await self._cache.get_or_fetch(
            key,
            lambda: self._fetch_snapshot(
                counter_id=counter_id,
                oauth_token=oauth_token,
                start=start,
                end_exclusive=end_exclusive,
            ),
        )

    async def _fetch_snapshot(
        self,
        *,
        counter_id: str,
        oauth_token: str,
        start: date,
        end_exclusive: date,
    ) -> MarketingSnapshot:
        params = {
            "ids": counter_id,
            "date1": start.isoformat(),
            "date2": (end_exclusive - timedelta(days=1)).isoformat(),
            "dimensions": "ym:s:lastTrafficSource",
            "metrics": "ym:s:visits",
            "accuracy": "full",
            "lang": "ru",
            "sort": "-ym:s:visits",
            "limit": "20",
        }
        async with self._client_factory() as client:
            response = await client.get(
                self.API_URL,
                params=params,
                headers={"Authorization": f"OAuth {oauth_token}"},
            )
            response.raise_for_status()
            payload = response.json()

        totals = payload.get("totals") if isinstance(payload, dict) else None
        visits = _nonnegative_int(totals[0] if isinstance(totals, list) and totals else 0)
        sources: list[MarketingSourceSnapshot] = []
        for row in payload.get("data", []) if isinstance(payload, dict) else []:
            if not isinstance(row, dict):
                continue
            dimensions = row.get("dimensions")
            metrics = row.get("metrics")
            if not isinstance(dimensions, list) or not dimensions:
                continue
            dimension = dimensions[0] if isinstance(dimensions[0], dict) else {}
            name = str(dimension.get("name") or dimension.get("id") or "Other")
            source_visits = _nonnegative_int(
                metrics[0] if isinstance(metrics, list) and metrics else 0
            )
            sources.append(
                MarketingSourceSnapshot(
                    name=name,
                    visits=source_visits,
                    share_pct=round(source_visits * 100 / visits, 2) if visits else 0.0,
                )
            )
        return MarketingSnapshot(
            status="fresh",
            visits=visits,
            sources=tuple(sources),
            updated_at=datetime.now().astimezone(),
        )


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return 0


_PROCESS_CACHE = MarketingSnapshotCache(
    ttl_seconds=settings.DASHBOARD_METRIKA_CACHE_TTL_SECONDS,
)
