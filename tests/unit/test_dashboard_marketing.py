from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from models.tenancy import TenantScope
from services import dashboard_marketing
from services.dashboard_marketing import (
    MarketingSnapshot,
    MarketingSnapshotCache,
    YandexMetrikaMarketingProvider,
    resolve_metrika_counter_id,
)
from services.analytics_connection_service import AnalyticsRuntimeCredentials


SYSTEM_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
SECONDARY_SYSTEM_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=2,
    is_system=True,
    is_canonical_storefront=False,
)
TENANT_SCOPE = TenantScope(tenant_id=2, storefront_id=7, is_system=False)


def test_counter_resolution_is_exactly_storefront_scoped():
    configured = '{"1:1": "111", "2:7": "777", "2:8": "888"}'

    assert resolve_metrika_counter_id(
        TENANT_SCOPE,
        scoped_counters_json=configured,
    ) == "777"
    assert resolve_metrika_counter_id(
        TenantScope(tenant_id=2, storefront_id=9, is_system=False),
        scoped_counters_json=configured,
    ) is None
    assert resolve_metrika_counter_id(
        SYSTEM_SCOPE,
        scoped_counters_json=configured,
    ) == "111"
    assert resolve_metrika_counter_id(
        SECONDARY_SYSTEM_SCOPE,
        scoped_counters_json=configured,
    ) is None


def test_system_storefronts_without_exact_mapping_fail_closed():
    assert resolve_metrika_counter_id(
        SYSTEM_SCOPE,
        scoped_counters_json="{}",
    ) is None
    assert resolve_metrika_counter_id(
        SECONDARY_SYSTEM_SCOPE,
        scoped_counters_json="{}",
    ) is None


@pytest.mark.asyncio
async def test_provider_maps_unconfigured_without_http_call():
    provider = YandexMetrikaMarketingProvider(
        oauth_token="",
        scoped_counters_json='{"1:1": "111"}',
    )

    snapshot = await provider.get_snapshot(
        tenant_scope=SYSTEM_SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 2),
    )

    assert snapshot.status == "unconfigured"
    assert snapshot.visits is None


@pytest.mark.asyncio
async def test_secondary_system_storefront_without_mapping_is_unconfigured():
    def unexpected_client():
        raise AssertionError("provider must not call HTTP without an exact mapping")

    provider = YandexMetrikaMarketingProvider(
        oauth_token="test-token",
        scoped_counters_json='{"1:1": "111"}',
        client_factory=unexpected_client,
    )

    snapshot = await provider.get_snapshot(
        tenant_scope=SECONDARY_SYSTEM_SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 2),
    )

    assert snapshot.status == "unconfigured"
    assert snapshot.visits is None


@pytest.mark.asyncio
async def test_provider_parses_visits_and_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "OAuth test-token"
        assert request.url.params["date2"] == "2026-08-02"
        return httpx.Response(
            200,
            json={
                "totals": [10.0],
                "data": [
                    {
                        "dimensions": [{"id": "organic", "name": "Search"}],
                        "metrics": [6.0],
                    },
                    {
                        "dimensions": [{"id": "direct", "name": "Direct"}],
                        "metrics": [4.0],
                    },
                ],
            },
        )

    provider = YandexMetrikaMarketingProvider(
        oauth_token="test-token",
        scoped_counters_json='{"1:1": "111"}',
        cache=MarketingSnapshotCache(ttl_seconds=60),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    snapshot = await provider.get_snapshot(
        tenant_scope=SYSTEM_SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 3),
    )

    assert snapshot.status == "fresh"
    assert snapshot.visits == 10
    assert [(source.name, source.visits, source.share_pct) for source in snapshot.sources] == [
        ("Search", 6, 60.0),
        ("Direct", 4, 40.0),
    ]


@pytest.mark.asyncio
async def test_storefront_connection_overrides_legacy_environment(monkeypatch):
    credentials = AsyncMock(
        return_value=AnalyticsRuntimeCredentials(
            counter_id="777",
            oauth_token="stored-token",
            fingerprint="stored-fingerprint",
        )
    )
    monkeypatch.setattr(
        dashboard_marketing.AnalyticsConnectionService,
        "get_metrika_runtime_credentials",
        credentials,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "OAuth stored-token"
        assert request.url.params["ids"] == "777"
        return httpx.Response(200, json={"totals": [3.0], "data": []})

    provider = YandexMetrikaMarketingProvider(
        oauth_token="legacy-token",
        scoped_counters_json='{"2:7": "111"}',
        cache=MarketingSnapshotCache(ttl_seconds=0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    snapshot = await provider.get_snapshot(
        session=object(),
        tenant_scope=TENANT_SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 2),
    )

    assert snapshot.status == "fresh"
    assert snapshot.visits == 3
    credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_returns_fresh_then_stale_on_refresh_error(monkeypatch):
    clock = iter([100.0, 101.0, 200.0, 201.0])
    monkeypatch.setattr(dashboard_marketing, "monotonic", lambda: next(clock))
    cache = MarketingSnapshotCache(ttl_seconds=10)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            return MarketingSnapshot(status="fresh", visits=5)
        raise RuntimeError("temporary provider failure")

    first = await cache.get_or_fetch("key", fetch)
    cached = await cache.get_or_fetch("key", fetch)
    stale = await cache.get_or_fetch("key", fetch)

    assert first.status == "fresh"
    assert cached.status == "fresh"
    assert stale.status == "stale"
    assert stale.visits == 5
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_maps_initial_provider_failure_to_error():
    cache = MarketingSnapshotCache(ttl_seconds=10)

    async def fail():
        raise httpx.ConnectError("offline")

    result = await cache.get_or_fetch("key", fail)

    assert result.status == "error"
    assert result.visits is None
