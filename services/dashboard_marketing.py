from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Awaitable, Callable, Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.tenancy import TenantScope
from services.analytics_connection_service import AnalyticsConnectionService
from services.analytics_google_providers import (
    GoogleAdsProvider,
    GoogleAnalyticsProvider,
    access_token as google_access_token,
)
from services.analytics_provider_types import (
    AdvertisingSnapshot,
    AnalyticsProviderError,
    GoogleAnalyticsSnapshot,
)
from services.analytics_yandex_providers import YandexDirectProvider


logger = logging.getLogger(__name__)


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
    ad_spend: float | None = None
    clicks: int | None = None
    impressions: int | None = None
    ctr: float | None = None
    platform_conversions: float | None = None
    currency: str | None = None
    providers: tuple["MarketingProviderSnapshot", ...] = ()
    bounce_rate: float | None = None
    average_session_duration_seconds: float | None = None


@dataclass(frozen=True)
class MarketingProviderSnapshot:
    provider: str
    status: MarketingStatus
    visits: int | None = None
    sessions: int | None = None
    active_users: int | None = None
    bounce_rate: float | None = None
    engagement_rate: float | None = None
    average_session_duration_seconds: float | None = None
    ad_spend: float | None = None
    clicks: int | None = None
    impressions: int | None = None
    ctr: float | None = None
    platform_conversions: float | None = None
    currency: str | None = None
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
                        message="Analytics providers are temporarily unavailable; cached data is shown.",
                    )
                return MarketingSnapshot(
                    status="error",
                    message="Analytics providers are temporarily unavailable.",
                )
            if snapshot.status == "error" and cached:
                return replace(
                    cached.snapshot,
                    status="stale",
                    message="Analytics providers are temporarily unavailable; cached data is shown.",
                )
            self._entries[key] = _CacheEntry(
                stored_at=monotonic(),
                snapshot=snapshot,
            )
            return snapshot


def _log_google_provider_failure(provider: str, error: Exception) -> None:
    if isinstance(error, AnalyticsProviderError):
        logger.warning(
            "DASHBOARD_GOOGLE_PROVIDER_FAILED provider=%s error_code=%s retryable=%s",
            provider,
            error.code,
            error.retryable,
        )
        return
    logger.warning(
        "DASHBOARD_GOOGLE_PROVIDER_FAILED provider=%s error_code=unexpected error_type=%s",
        provider,
        type(error).__name__,
    )


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
            "metrics": "ym:s:visits,ym:s:bounceRate,ym:s:avgVisitDurationSeconds",
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
        bounce_rate = _optional_nonnegative_float(totals, 1)
        average_duration = _optional_nonnegative_float(totals, 2)
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
            bounce_rate=bounce_rate,
            average_session_duration_seconds=average_duration,
        )


class IntegratedMarketingProvider:
    """Combine traffic and advertising sources after exact storefront resolution."""

    def __init__(
        self,
        *,
        metrika_provider: YandexMetrikaMarketingProvider | None = None,
        cache: MarketingSnapshotCache | None = None,
    ) -> None:
        self._metrika = metrika_provider or YandexMetrikaMarketingProvider()
        self._cache = cache or _INTEGRATED_CACHE

    async def get_snapshot(
        self,
        *,
        session: AsyncSession,
        tenant_scope: TenantScope,
        start: date,
        end_exclusive: date,
    ) -> MarketingSnapshot:
        connections = await AnalyticsConnectionService.get_runtime_connections(
            session,
            tenant_scope=tenant_scope,
        )
        fingerprints = ":".join(
            f"{provider}={connection.fingerprint}"
            for provider, connection in sorted(connections.items())
        )
        key = (
            f"integrated:{tenant_scope.tenant_id}:{tenant_scope.storefront_id}:"
            f"{fingerprints}:{start.isoformat()}:{end_exclusive.isoformat()}"
        )
        return await self._cache.get_or_fetch(
            key,
            lambda: self._fetch_snapshot(
                session=session,
                tenant_scope=tenant_scope,
                connections=connections,
                start=start,
                end_exclusive=end_exclusive,
            ),
        )

    async def _fetch_snapshot(
        self,
        *,
        session: AsyncSession,
        tenant_scope: TenantScope,
        connections,
        start: date,
        end_exclusive: date,
    ) -> MarketingSnapshot:
        metrika = await self._metrika.get_snapshot(
            session=session,
            tenant_scope=tenant_scope,
            start=start,
            end_exclusive=end_exclusive,
        )
        provider_rows: list[MarketingProviderSnapshot] = [
            MarketingProviderSnapshot(
                provider="yandex_metrika",
                status=metrika.status,
                visits=metrika.visits,
                bounce_rate=metrika.bounce_rate,
                average_session_duration_seconds=metrika.average_session_duration_seconds,
                message=metrika.message,
            )
        ]
        end = end_exclusive - timedelta(days=1)

        direct_connection = connections.get("yandex_direct")
        direct_snapshot: AdvertisingSnapshot | None = None
        if direct_connection is None:
            provider_rows.append(
                MarketingProviderSnapshot(provider="yandex_direct", status="unconfigured")
            )
        else:
            try:
                direct_snapshot = await asyncio.wait_for(
                    YandexDirectProvider().fetch(
                        str(direct_connection.credentials.get("oauth_token") or ""),
                        direct_connection.public_config,
                        start,
                        end,
                    ),
                    timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
                )
                provider_rows.append(_advertising_provider_row(direct_snapshot))
            except Exception:
                provider_rows.append(
                    MarketingProviderSnapshot(
                        provider="yandex_direct",
                        status="error",
                        message="Яндекс Директ временно недоступен.",
                    )
                )

        ga_connection = connections.get("google_analytics")
        ga_snapshot: GoogleAnalyticsSnapshot | None = None
        if ga_connection is None:
            provider_rows.append(
                MarketingProviderSnapshot(provider="google_analytics", status="unconfigured")
            )
        else:
            original = dict(ga_connection.credentials)
            try:
                token = await google_access_token(ga_connection.credentials)
                ga_snapshot = await asyncio.wait_for(
                    GoogleAnalyticsProvider().fetch(
                        token,
                        ga_connection.public_config,
                        start,
                        end,
                    ),
                    timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
                )
                provider_rows.append(
                    MarketingProviderSnapshot(
                        provider="google_analytics",
                        status="fresh",
                        sessions=ga_snapshot.sessions,
                        active_users=ga_snapshot.active_users,
                        engagement_rate=ga_snapshot.engagement_rate,
                        average_session_duration_seconds=ga_snapshot.average_session_duration_seconds,
                    )
                )
                if ga_connection.credentials != original:
                    await AnalyticsConnectionService.persist_refreshed_credentials(
                        session,
                        tenant_scope=tenant_scope,
                        provider="google_analytics",
                        credentials=ga_connection.credentials,
                    )
            except Exception as exc:
                _log_google_provider_failure("google_analytics", exc)
                provider_rows.append(
                    MarketingProviderSnapshot(
                        provider="google_analytics",
                        status="error",
                        message="Google Analytics временно недоступен.",
                    )
                )

        ads_connection = connections.get("google_ads")
        ads_snapshot: AdvertisingSnapshot | None = None
        if ads_connection is None:
            provider_rows.append(
                MarketingProviderSnapshot(provider="google_ads", status="unconfigured")
            )
        elif not settings.GOOGLE_ADS_DEVELOPER_TOKEN.strip():
            provider_rows.append(
                MarketingProviderSnapshot(
                    provider="google_ads",
                    status="error",
                    message="Google Ads не настроен на стороне CRM.",
                )
            )
        else:
            original = dict(ads_connection.credentials)
            try:
                token = await google_access_token(ads_connection.credentials)
                ads_snapshot = await asyncio.wait_for(
                    GoogleAdsProvider(
                        developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN.strip()
                    ).fetch(token, ads_connection.public_config, start, end),
                    timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
                )
                provider_rows.append(_advertising_provider_row(ads_snapshot))
                if ads_connection.credentials != original:
                    await AnalyticsConnectionService.persist_refreshed_credentials(
                        session,
                        tenant_scope=tenant_scope,
                        provider="google_ads",
                        credentials=ads_connection.credentials,
                    )
            except Exception as exc:
                _log_google_provider_failure("google_ads", exc)
                provider_rows.append(
                    MarketingProviderSnapshot(
                        provider="google_ads",
                        status="error",
                        message="Google Ads временно недоступен.",
                    )
                )

        traffic_sources = metrika.sources
        visits = metrika.visits
        if visits is None and ga_snapshot is not None:
            visits = ga_snapshot.sessions
            traffic_sources = tuple(
                MarketingSourceSnapshot(
                    name=name,
                    visits=value,
                    share_pct=round(value * 100 / visits, 2) if visits else 0.0,
                )
                for name, value in sorted(
                    ga_snapshot.sources.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[:20]
            )

        advertising = [item for item in (direct_snapshot, ads_snapshot) if item is not None]
        currencies = {item.currency for item in advertising if item.currency}
        currency = next(iter(currencies)) if len(currencies) == 1 else None
        currencies_are_compatible = bool(currency) and all(
            item.currency == currency for item in advertising
        )
        spend = (
            round(sum(item.spend for item in advertising), 2)
            if advertising and currencies_are_compatible
            else None
        )
        clicks = sum(item.clicks for item in advertising) if advertising else None
        impressions = sum(item.impressions for item in advertising) if advertising else None
        conversions = (
            round(sum(item.conversions for item in advertising), 2)
            if advertising
            else None
        )
        statuses = {row.status for row in provider_rows}
        status: MarketingStatus = "fresh" if "fresh" in statuses else metrika.status
        if status == "unconfigured" and "error" in statuses:
            status = "error"
        return MarketingSnapshot(
            status=status,
            visits=visits,
            sources=traffic_sources,
            ad_spend=spend,
            clicks=clicks,
            impressions=impressions,
            ctr=(round(clicks * 100 / impressions, 2) if clicks is not None and impressions else None),
            platform_conversions=conversions,
            currency=currency if currencies_are_compatible else None,
            providers=tuple(provider_rows),
            updated_at=datetime.now().astimezone(),
        )


def _advertising_provider_row(snapshot: AdvertisingSnapshot) -> MarketingProviderSnapshot:
    return MarketingProviderSnapshot(
        provider=snapshot.provider,
        status="fresh",
        ad_spend=snapshot.spend,
        clicks=snapshot.clicks,
        impressions=snapshot.impressions,
        ctr=snapshot.ctr,
        platform_conversions=snapshot.conversions,
        currency=snapshot.currency,
    )


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return 0


def _optional_nonnegative_float(values: object, index: int) -> float | None:
    if not isinstance(values, list) or len(values) <= index:
        return None
    try:
        return round(max(0.0, float(values[index])), 2)
    except (TypeError, ValueError):
        return None


_PROCESS_CACHE = MarketingSnapshotCache(
    ttl_seconds=settings.DASHBOARD_METRIKA_CACHE_TTL_SECONDS,
)

_INTEGRATED_CACHE = MarketingSnapshotCache(
    ttl_seconds=settings.ANALYTICS_PROVIDER_CACHE_TTL_SECONDS,
)
