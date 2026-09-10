from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from models.tenancy import TenantScope
from services import dashboard_marketing as marketing, dashboard_search_demand as search
from services.analytics_connection_contracts import AnalyticsConnectionError, AnalyticsRuntimeConnection
from services.dashboard_overview_service import _marketing_schema, _search_demand_schema


SCOPE = TenantScope(tenant_id=2, storefront_id=7)
PERIOD = {"start": date(2026, 9, 1), "end_exclusive": date(2026, 9, 11)}
SAVED_AT = datetime(2026, 9, 9, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_metrika_decryption_error_does_not_fall_back_to_environment(monkeypatch):
    monkeypatch.setattr(marketing.AnalyticsConnectionService, "get_metrika_runtime_credentials",
                        AsyncMock(side_effect=AnalyticsConnectionError("credentials_unreadable", "private-detail")))
    provider = marketing.YandexMetrikaMarketingProvider(
        oauth_token="environment-token", scoped_counters_json='{"2:7":"123"}',
    )
    fetch = AsyncMock()
    monkeypatch.setattr(provider, "_fetch_snapshot", fetch)
    result = await provider.get_snapshot(session=object(), tenant_scope=SCOPE, **PERIOD)
    assert result.status == "error"
    assert result.updated_at is None
    assert "Подключение сохранено" in result.message
    assert "private-detail" not in result.message
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_unreadable_integrations_never_call_providers(monkeypatch):
    connections = {name: AnalyticsRuntimeConnection(
        provider=name, public_config={}, credentials={}, fingerprint=name,
        error_code="credentials_unreadable",
    ) for name in ("yandex_direct", "google_analytics", "google_ads", "yandex_webmaster", "google_search_console")}
    monkeypatch.setattr(marketing.AnalyticsConnectionService, "get_runtime_connections", AsyncMock(return_value=connections))
    forbidden = AsyncMock(side_effect=AssertionError("must not send unreadable credentials"))
    for module, names in ((marketing, ("YandexDirectProvider", "GoogleAnalyticsProvider", "GoogleAdsProvider")),
                          (search, ("YandexWebmasterProvider", "GoogleSearchConsoleProvider"))):
        for name in names:
            monkeypatch.setattr(getattr(module, name), "fetch", forbidden)
    metrika = AsyncMock()
    metrika.get_snapshot.return_value = marketing.MarketingSnapshot(status="error")
    result = await marketing.IntegratedMarketingProvider(
        metrika_provider=metrika, cache=marketing.MarketingSnapshotCache(ttl_seconds=0),
    ).get_snapshot(session=object(), tenant_scope=SCOPE, **PERIOD)
    demand = await search.IntegratedSearchDemandProvider(cache=search.SearchDemandCache(0)).get_snapshot(
        session=object(), tenant_scope=SCOPE, **PERIOD,
    )
    assert result.status == demand.status == "error"
    assert result.updated_at is demand.updated_at is None
    assert all(row.status == "error" for row in (*result.providers, *demand.providers))
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_missing_sources_have_no_fabricated_updated_time(monkeypatch):
    monkeypatch.setattr(marketing.AnalyticsConnectionService, "get_runtime_connections", AsyncMock(return_value={}))
    metrika = AsyncMock()
    metrika.get_snapshot.return_value = marketing.MarketingSnapshot(status="unconfigured")
    result = await marketing.IntegratedMarketingProvider(
        metrika_provider=metrika, cache=marketing.MarketingSnapshotCache(ttl_seconds=0),
    ).get_snapshot(session=object(), tenant_scope=SCOPE, **PERIOD)
    assert result.status == "unconfigured"
    assert result.updated_at is None


@pytest.mark.parametrize("kind", ["marketing", "search"])
@pytest.mark.asyncio
async def test_cache_failure_marks_source_stale_and_preserves_success_time(kind):
    if kind == "marketing":
        cache = marketing.MarketingSnapshotCache(ttl_seconds=0)
        snapshot = marketing.MarketingSnapshot(status="fresh", updated_at=SAVED_AT, providers=(
            marketing.MarketingProviderSnapshot("yandex_metrika", "fresh", visits=10, updated_at=SAVED_AT),
        ))
    else:
        cache = search.SearchDemandCache(0)
        snapshot = search.SearchDemandSnapshot(status="fresh", updated_at=SAVED_AT, providers=(
            search.SearchDemandProviderState("yandex_webmaster", "fresh", updated_at=SAVED_AT),
        ))
    await cache.get_or_fetch("same-scope-period", AsyncMock(return_value=snapshot))
    result = await cache.get_or_fetch("same-scope-period", AsyncMock(side_effect=RuntimeError("offline")))
    assert result.status == result.providers[0].status == "stale"
    assert result.updated_at == result.providers[0].updated_at == SAVED_AT


@pytest.mark.parametrize("kind", ["marketing", "search"])
@pytest.mark.asyncio
async def test_cache_does_not_treat_failed_attempt_as_previous_success(kind):
    cache = marketing.MarketingSnapshotCache(ttl_seconds=0) if kind == "marketing" else search.SearchDemandCache(0)
    snapshot = marketing.MarketingSnapshot(status="error") if kind == "marketing" else search.SearchDemandSnapshot(status="error")
    await cache.get_or_fetch("same-scope-period", AsyncMock(return_value=snapshot))
    result = await cache.get_or_fetch("same-scope-period", AsyncMock(return_value=snapshot))
    assert result.status == "error"
    assert result.updated_at is None


def test_api_preserves_each_source_success_timestamp():
    result = _marketing_schema(marketing.MarketingSnapshot(status="fresh", providers=(
        marketing.MarketingProviderSnapshot("yandex_metrika", "fresh", updated_at=SAVED_AT),
    )), leads=0, acquired_customers=0)
    demand = _search_demand_schema(search.SearchDemandSnapshot(status="fresh", providers=(
        search.SearchDemandProviderState("yandex_webmaster", "fresh", updated_at=SAVED_AT),
    )))
    assert result.providers[0].updated_at == demand.providers[0].updated_at == SAVED_AT
