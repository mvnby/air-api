"""Uncached, one-source refreshes for durable dashboard analytics snapshots.

Only the background snapshot worker calls this module. It deliberately does not
own a session or schedule work, and never mixes a failed source with a success.
"""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import AnalyticsConnection
from models.tenancy import TenantScope
from services.analytics_connection_service import AnalyticsConnectionService, AnalyticsCredentialCipher
from services.analytics_google_providers import (
    GoogleAdsProvider, GoogleAnalyticsProvider, GoogleSearchConsoleProvider,
    access_token as google_access_token,
)
from services.analytics_yandex_providers import YandexDirectProvider, YandexWebmasterProvider
from services.dashboard_marketing import (
    MarketingProviderSnapshot, MarketingSnapshot, MarketingSourceSnapshot,
    YandexMetrikaMarketingProvider, _advertising_provider_row, resolve_metrika_counter_id,
)
from services.dashboard_search_demand import (
    SearchDemandProviderState, SearchDemandSnapshot, _queries,
)

PROVIDERS = frozenset({
    "yandex_metrika", "yandex_direct", "yandex_webmaster",
    "google_analytics", "google_ads", "google_search_console",
})


class SourceFetchError(ValueError):
    """A fixed error code; provider payloads and credentials must not escape."""

    def __init__(self, code: str = "provider_unavailable") -> None:
        self.code = code
        super().__init__(code)


async def fetch_source(
    session: AsyncSession,
    tenant_scope: TenantScope,
    provider: str,
    start: date,
    end_exclusive: date,
) -> dict[str, Any]:
    """Fetch precisely one source, with an overall deadline including OAuth.

    Google token rotation is persisted through the existing connection service
    before requesting its report, even if that report subsequently fails. That
    service commits the passed worker-owned session; callers must not combine
    this call with an uncommitted claim or unrelated transaction.
    """
    if provider not in PROVIDERS:
        raise SourceFetchError("unsupported_provider")
    if end_exclusive <= start:
        raise SourceFetchError("invalid_period")
    try:
        return await asyncio.wait_for(
            _fetch(session, tenant_scope, provider, start, end_exclusive),
            timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS,
        )
    except SourceFetchError:
        raise
    except TimeoutError:
        raise SourceFetchError("provider_timeout") from None
    except Exception:
        raise SourceFetchError() from None


async def _fetch(session, scope, provider, start, end_exclusive):
    connection = await AnalyticsConnectionService._get_connection(
        session, tenant_scope=scope, provider=provider,
    )
    if connection is None:
        if provider != "yandex_metrika" or not scope.is_system:
            raise SourceFetchError("source_unconfigured")
        config = {"counter_id": resolve_metrika_counter_id(
            scope, scoped_counters_json=settings.DASHBOARD_METRIKA_STOREFRONT_COUNTERS_JSON,
        )}
        credentials = {"oauth_token": settings.DASHBOARD_METRIKA_OAUTH_TOKEN.strip()}
    else:
        if connection.status != "active":
            raise SourceFetchError("source_unconfigured")
        config = dict(connection.public_config or {})
        try:
            credentials = AnalyticsCredentialCipher.decrypt(
                connection.encrypted_credentials, tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id, provider=provider,
            )
        except Exception:
            raise SourceFetchError("credentials_unavailable") from None

    end = end_exclusive - timedelta(days=1)
    now = datetime.now(timezone.utc)
    if provider == "yandex_metrika":
        counter = str(config.get("counter_id") or "")
        token = str(credentials.get("oauth_token") or "").strip()
        if not counter.isdigit() or not token:
            raise SourceFetchError("credentials_unavailable")
        snapshot = await YandexMetrikaMarketingProvider(
            client_factory=_metrika_client,
        )._fetch_snapshot(
            counter_id=counter, oauth_token=token, start=start, end_exclusive=end_exclusive,
        )
        if snapshot.status != "fresh" or snapshot.visits is None:
            raise SourceFetchError()
        row = MarketingProviderSnapshot(
            provider=provider, status="fresh", visits=snapshot.visits,
            bounce_rate=snapshot.bounce_rate,
            average_session_duration_seconds=snapshot.average_session_duration_seconds,
            updated_at=snapshot.updated_at,
        )
        return _payload("marketing", replace(snapshot, providers=(row,)))

    if provider.startswith("google_"):
        if provider == "google_ads" and not settings.GOOGLE_ADS_DEVELOPER_TOKEN.strip():
            raise SourceFetchError("provider_not_configured")
        original = dict(credentials)
        expected = (connection.id, connection.snapshot_revision, dict(config), connection.credentials_fingerprint)
        token = await google_access_token(credentials)
        if credentials != original:
            await _persist_credentials(session, scope, provider, credentials, expected)
    else:
        token = str(credentials.get("oauth_token") or "").strip()
    if not token:
        raise SourceFetchError("credentials_unavailable")

    if provider in {"yandex_direct", "google_ads"}:
        adapter = (YandexDirectProvider() if provider == "yandex_direct" else
                   GoogleAdsProvider(developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN.strip()))
        advertising = await adapter.fetch(token, config, start, end)
        row = _advertising_provider_row(advertising)
        return _payload("marketing", MarketingSnapshot(
            status="fresh", ad_spend=advertising.spend, clicks=advertising.clicks,
            impressions=advertising.impressions, ctr=advertising.ctr,
            platform_conversions=advertising.conversions, currency=advertising.currency,
            providers=(row,), updated_at=row.updated_at,
        ))
    if provider == "google_analytics":
        traffic = await GoogleAnalyticsProvider().fetch(token, config, start, end)
        visits = traffic.sessions
        sources = tuple(MarketingSourceSnapshot(
            name=name, visits=value,
            share_pct=round(value * 100 / visits, 2) if visits else 0.0,
        ) for name, value in sorted(traffic.sources.items(), key=lambda item: item[1], reverse=True)[:20])
        row = MarketingProviderSnapshot(
            provider=provider, status="fresh", sessions=visits, active_users=traffic.active_users,
            engagement_rate=traffic.engagement_rate,
            average_session_duration_seconds=traffic.average_session_duration_seconds,
            updated_at=now,
        )
        return _payload("marketing", MarketingSnapshot(
            status="fresh", visits=visits, sources=sources, providers=(row,), updated_at=now,
            average_session_duration_seconds=traffic.average_session_duration_seconds,
        ))
    if provider == "yandex_webmaster":
        search = await YandexWebmasterProvider().fetch(
            token, config, limit=500, period_start=start, period_end=end,
        )
    else:
        search = await GoogleSearchConsoleProvider().fetch(token, config, start, end, limit=500)
    queries = sorted(_queries(provider, search.rows), key=lambda row: (row.clicks, row.impressions), reverse=True)
    return _payload("search", SearchDemandSnapshot(
        status="fresh", queries=tuple(queries[:1000]),
        providers=(SearchDemandProviderState(provider, "fresh", updated_at=now),),
        updated_at=now,
        message="Часть редких запросов поисковые системы могут скрывать; свежие данные появляются с задержкой.",
    ))



async def _persist_credentials(session, scope, provider, credentials, expected):
    # Re-read after OAuth I/O, bypassing the session identity map. Lock only for
    # this short write, never for the external report request.
    current = (await session.execute(select(AnalyticsConnection).where(
        AnalyticsConnection.tenant_id == scope.tenant_id,
        AnalyticsConnection.storefront_id == scope.storefront_id,
        AnalyticsConnection.provider == provider,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if current is None or current.status != "active" or (
        current.id, current.snapshot_revision, dict(current.public_config or {}),
        current.credentials_fingerprint,
    ) != expected:
        raise SourceFetchError("source_changed")
    await AnalyticsConnectionService.persist_refreshed_credentials(
        session, tenant_scope=scope, provider=provider, credentials=credentials,
    )


def _payload(kind: str, snapshot) -> dict[str, Any]:
    # JSON validation rejects NaN/infinity as well as accidentally leaked objects.
    return {kind: json.loads(json.dumps(asdict(snapshot), default=_json_default, allow_nan=False))}


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("snapshot_not_serializable")


async def _validate_metrika_response(response: httpx.Response) -> None:
    response.raise_for_status()
    await response.aread()
    payload = response.json()
    totals = payload.get("totals") if isinstance(payload, dict) else None
    if not isinstance(totals, list) or not totals:
        raise SourceFetchError("provider_invalid_response")
    try:
        visits = float(totals[0])
    except (TypeError, ValueError):
        raise SourceFetchError("provider_invalid_response") from None
    if not math.isfinite(visits) or visits < 0:
        raise SourceFetchError("provider_invalid_response")


def _metrika_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.ANALYTICS_PROVIDER_TIMEOUT_SECONDS, trust_env=False,
        event_hooks={"response": [_validate_metrika_response]},
    )
