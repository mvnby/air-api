from datetime import date
from unittest.mock import AsyncMock

import pytest

from models.tenancy import TenantScope
from services import dashboard_marketing, dashboard_search_demand
from services.analytics_connection_service import AnalyticsRuntimeConnection
from services.analytics_provider_types import (
    AdvertisingSnapshot,
    SearchDemandProviderSnapshot,
    SearchQueryRow,
)
from services.dashboard_marketing import (
    IntegratedMarketingProvider,
    MarketingSnapshot,
    MarketingSnapshotCache,
)
from services.dashboard_overview_service import _marketing_schema
from services.dashboard_search_demand import IntegratedSearchDemandProvider, SearchDemandCache


SCOPE = TenantScope(tenant_id=2, storefront_id=7)


@pytest.mark.asyncio
async def test_integrated_marketing_combines_metrika_and_direct(monkeypatch):
    metrika = AsyncMock()
    metrika.get_snapshot.return_value = MarketingSnapshot(status="fresh", visits=120)
    connection = AnalyticsRuntimeConnection(
        provider="yandex_direct",
        public_config={"client_login": "vitebsk"},
        credentials={"oauth_token": "secret-token"},
        fingerprint="fingerprint",
    )
    monkeypatch.setattr(
        dashboard_marketing.AnalyticsConnectionService,
        "get_runtime_connections",
        AsyncMock(return_value={"yandex_direct": connection}),
    )

    class DirectStub:
        async def fetch(self, token, config, start, end):
            assert token == "secret-token"
            assert config["client_login"] == "vitebsk"
            return AdvertisingSnapshot(
                "yandex_direct", start, end, 1_000, 50, 500.0, 4.0, "BYN"
            )

    monkeypatch.setattr(dashboard_marketing, "YandexDirectProvider", DirectStub)
    snapshot = await IntegratedMarketingProvider(
        metrika_provider=metrika,
        cache=MarketingSnapshotCache(ttl_seconds=0),
    ).get_snapshot(
        session=object(),
        tenant_scope=SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 3),
    )

    assert snapshot.visits == 120
    assert snapshot.ad_spend == 500.0
    assert snapshot.clicks == 50
    assert snapshot.impressions == 1_000
    assert snapshot.ctr == 5.0
    assert snapshot.platform_conversions == 4.0


@pytest.mark.asyncio
async def test_integrated_marketing_does_not_sum_mixed_advertising_currencies(monkeypatch):
    metrika = AsyncMock()
    metrika.get_snapshot.return_value = MarketingSnapshot(status="fresh", visits=120)
    connections = {
        "yandex_direct": AnalyticsRuntimeConnection(
            provider="yandex_direct",
            public_config={"currency": "BYN"},
            credentials={"oauth_token": "direct-token"},
            fingerprint="direct",
        ),
        "google_ads": AnalyticsRuntimeConnection(
            provider="google_ads",
            public_config={"customer_id": "1234567890"},
            credentials={"access_token": "google-token"},
            fingerprint="ads",
        ),
    }
    monkeypatch.setattr(
        dashboard_marketing.AnalyticsConnectionService,
        "get_runtime_connections",
        AsyncMock(return_value=connections),
    )
    monkeypatch.setattr(
        dashboard_marketing,
        "google_access_token",
        AsyncMock(return_value="google-token"),
    )
    monkeypatch.setattr(
        dashboard_marketing.settings,
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "system-token",
    )

    class DirectStub:
        async def fetch(self, _token, _config, start, end):
            return AdvertisingSnapshot(
                "yandex_direct", start, end, 1_000, 50, 500.0, 4.0, "BYN"
            )

    class AdsStub:
        def __init__(self, *, developer_token):
            assert developer_token == "system-token"

        async def fetch(self, _token, _config, start, end):
            return AdvertisingSnapshot(
                "google_ads", start, end, 2_000, 80, 300.0, 6.0, "USD"
            )

    monkeypatch.setattr(dashboard_marketing, "YandexDirectProvider", DirectStub)
    monkeypatch.setattr(dashboard_marketing, "GoogleAdsProvider", AdsStub)

    snapshot = await IntegratedMarketingProvider(
        metrika_provider=metrika,
        cache=MarketingSnapshotCache(ttl_seconds=0),
    ).get_snapshot(
        session=object(),
        tenant_scope=SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 3),
    )

    assert snapshot.ad_spend is None
    assert snapshot.currency is None
    assert snapshot.clicks == 130
    assert {row.currency for row in snapshot.providers if row.ad_spend is not None} == {
        "BYN",
        "USD",
    }


def test_marketing_schema_uses_crm_counts_for_cpl_and_cac():
    result = _marketing_schema(
        MarketingSnapshot(status="fresh", ad_spend=600.0, platform_conversions=9.0),
        leads=12,
        acquired_customers=3,
    )

    assert result.cost_per_lead == 50.0
    assert result.customer_acquisition_cost == 200.0
    assert result.platform_conversions == 9.0


def test_marketing_schema_keeps_web_analytics_metrics_provider_specific():
    result = _marketing_schema(
        MarketingSnapshot(
            status="fresh",
            providers=(
                dashboard_marketing.MarketingProviderSnapshot(
                    provider="yandex_metrika",
                    status="fresh",
                    visits=120,
                    bounce_rate=18.5,
                    average_session_duration_seconds=82.0,
                ),
                dashboard_marketing.MarketingProviderSnapshot(
                    provider="google_analytics",
                    status="fresh",
                    sessions=95,
                    active_users=71,
                    engagement_rate=64.2,
                    average_session_duration_seconds=77.0,
                ),
            ),
        ),
        leads=0,
        acquired_customers=0,
    )

    metrika, ga4 = result.providers
    assert metrika.bounce_rate == 18.5
    assert metrika.ad_spend is None
    assert ga4.sessions == 95
    assert ga4.active_users == 71
    assert ga4.engagement_rate == 64.2


@pytest.mark.asyncio
async def test_search_demand_merges_exact_storefront_provider_rows(monkeypatch):
    connection = AnalyticsRuntimeConnection(
        provider="yandex_webmaster",
        public_config={"user_id": "42", "host_id": "https:mvn.by:443"},
        credentials={"oauth_token": "secret-token"},
        fingerprint="fingerprint",
    )
    monkeypatch.setattr(
        dashboard_search_demand.AnalyticsConnectionService,
        "get_runtime_connections",
        AsyncMock(return_value={"yandex_webmaster": connection}),
    )

    class WebmasterStub:
        async def fetch(self, token, config, *, limit, period_start, period_end):
            assert token == "secret-token"
            assert config["host_id"] == "https:mvn.by:443"
            assert period_start == date(2026, 8, 1)
            assert period_end == date(2026, 8, 2)
            assert limit == 500
            return SearchDemandProviderSnapshot(
                "yandex_webmaster",
                (
                    SearchQueryRow("кондиционер витебск", 8, 100, 8.0, 3.4),
                    SearchQueryRow("монтаж кондиционера", 3, 60, 5.0, 5.2),
                ),
            )

    monkeypatch.setattr(
        dashboard_search_demand,
        "YandexWebmasterProvider",
        WebmasterStub,
    )
    snapshot = await IntegratedSearchDemandProvider(
        cache=SearchDemandCache(ttl_seconds=0)
    ).get_snapshot(
        session=object(),
        tenant_scope=SCOPE,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 8, 3),
    )

    assert snapshot.status == "fresh"
    assert [row.query for row in snapshot.queries] == [
        "кондиционер витебск",
        "монтаж кондиционера",
    ]
    assert snapshot.providers[1].provider == "google_search_console"
    assert snapshot.providers[1].status == "unconfigured"
