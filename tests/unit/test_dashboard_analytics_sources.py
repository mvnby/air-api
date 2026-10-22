import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from models.tenancy import TenantScope
from services import dashboard_analytics_sources as sources
from services.analytics_provider_types import (
    AdvertisingSnapshot, GoogleAnalyticsSnapshot, SearchDemandProviderSnapshot, SearchQueryRow,
)

SCOPE = TenantScope(2, 7)
START = date(2026, 10, 1)
END = date(2026, 11, 1)


def connection(provider):
    return SimpleNamespace(
        id=11, tenant_id=2, storefront_id=7, provider=provider, status="active",
        snapshot_revision="configuration-v1", credentials_fingerprint="fingerprint-v1",
        encrypted_credentials="ciphertext", public_config={"counter_id": "123"},
    )


@pytest.fixture
def runtime(monkeypatch):
    getter = AsyncMock()
    getter.return_value = connection("google_analytics")
    monkeypatch.setattr(sources.AnalyticsConnectionService, "_get_connection", getter)
    monkeypatch.setattr(sources.AnalyticsCredentialCipher, "decrypt", Mock(return_value={
        "oauth_token": "yandex-secret", "access_token": "google-secret",
    }))
    monkeypatch.setattr(sources, "google_access_token", AsyncMock(return_value="google-secret"))
    monkeypatch.setattr(sources.settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "developer-secret")
    monkeypatch.setattr(sources.settings, "ANALYTICS_PROVIDER_TIMEOUT_SECONDS", 1)
    return getter


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", sorted(sources.PROVIDERS))
async def test_one_source_fetch_does_not_call_other_providers_and_is_json_ready(monkeypatch, runtime, provider):
    runtime.return_value = connection(provider)
    calls = []

    def adapter(name):
        class Adapter:
            def __init__(self, **kwargs):
                if name == "google_ads":
                    assert kwargs == {"developer_token": "developer-secret"}

            async def fetch(self, token, config, *period, **kwargs):
                assert name == provider
                calls.append((name, token, config, period, kwargs))
                if name in {"yandex_direct", "google_ads"}:
                    return AdvertisingSnapshot(name, START, date(2026, 10, 31), 100, 4, 12.5, 2.0, "BYN")
                if name == "google_analytics":
                    return GoogleAnalyticsSnapshot(100, 70, .6, 51.0, {"search": 80, "direct": 20})
                return SearchDemandProviderSnapshot(name, (
                    SearchQueryRow("air", 4, 100, 4.0, 3.0),
                    SearchQueryRow(" ", 0, 1, 0.0, None),
                ))
        return Adapter

    for name, symbol in {
        "yandex_direct": "YandexDirectProvider", "google_ads": "GoogleAdsProvider",
        "google_analytics": "GoogleAnalyticsProvider", "yandex_webmaster": "YandexWebmasterProvider",
        "google_search_console": "GoogleSearchConsoleProvider",
    }.items():
        monkeypatch.setattr(sources, symbol, adapter(name))

    metrika = AsyncMock(side_effect=AssertionError("unrelated Metrika call"))
    if provider == "yandex_metrika":
        def transport(request):
            assert request.url.params["date2"] == "2026-10-31"
            assert request.headers["Authorization"] == "OAuth yandex-secret"
            calls.append(("yandex_metrika",))
            return httpx.Response(200, json={"totals": [120, 14.5, 61.2], "data": []})
        monkeypatch.setattr(sources, "_metrika_client", lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(transport),
            event_hooks={"response": [sources._validate_metrika_response]},
        ))
    else:
        monkeypatch.setattr(sources.YandexMetrikaMarketingProvider, "_fetch_snapshot", metrika)

    session = object()
    result = await sources.fetch_source(session, SCOPE, provider, START, END)
    assert len(calls) == 1
    runtime.assert_awaited_once_with(session, tenant_scope=SCOPE, provider=provider)
    payload = result["search" if provider in {"yandex_webmaster", "google_search_console"} else "marketing"]
    assert payload["status"] == "fresh"
    assert payload["providers"][0]["provider"] == provider
    assert len(payload["providers"]) == 1
    serialized = json.dumps(result, allow_nan=False)
    assert "secret" not in serialized and "ciphertext" not in serialized
    assert isinstance(payload["updated_at"], str)
    if "search" in result:
        assert [row["query"] for row in payload["queries"]] == ["air"]
    elif provider == "google_analytics":
        assert payload["visits"] == 100
        assert payload["sources"][0] == {"name": "search", "visits": 80, "share_pct": 80.0}
    elif provider in {"yandex_direct", "google_ads"}:
        assert payload["ad_spend"] == 12.5 and payload["ctr"] == 4.0
    if provider != "yandex_metrika":
        metrika.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["oauth", "report"])
async def test_deadline_includes_oauth_and_report(monkeypatch, runtime, stage):
    monkeypatch.setattr(sources.settings, "ANALYTICS_PROVIDER_TIMEOUT_SECONDS", .01)
    async def hang(*args, **kwargs):
        await asyncio.Event().wait()
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", hang)
    if stage == "oauth":
        monkeypatch.setattr(sources, "google_access_token", hang)
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(object(), SCOPE, "google_analytics", START, END)
    assert error.value.code == "provider_timeout"


@pytest.mark.asyncio
async def test_provider_failure_is_not_a_zero_success_and_does_not_expose_secrets(monkeypatch, runtime):
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", AsyncMock(side_effect=ValueError("secret-token in https://provider")))
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(object(), SCOPE, "google_analytics", START, END)
    assert str(error.value) == "provider_unavailable"
    assert error.value.__suppress_context__


@pytest.mark.asyncio
async def test_rotated_google_tokens_persist_before_failed_report(monkeypatch, runtime):
    row = runtime.return_value
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: row)))
    async def rotate(credentials):
        credentials["access_token"] = "rotated-secret"
        return "rotated-secret"
    monkeypatch.setattr(sources, "google_access_token", rotate)
    persisted = AsyncMock()
    monkeypatch.setattr(sources.AnalyticsConnectionService, "persist_refreshed_credentials", persisted)
    async def fail_report(*args):
        persisted.assert_awaited_once()
        raise ValueError("report failed")
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", fail_report)
    with pytest.raises(sources.SourceFetchError):
        await sources.fetch_source(session, SCOPE, "google_analytics", START, END)
    assert persisted.await_args.args == (session,)
    assert persisted.await_args.kwargs["tenant_scope"] == SCOPE
    assert persisted.await_args.kwargs["credentials"]["access_token"] == "rotated-secret"
    statement = session.execute.await_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    assert statement._for_update_arg is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["deleted", "disabled", "recreated", "revision", "config", "credentials"])
async def test_token_refresh_cannot_overwrite_concurrently_changed_connection(monkeypatch, runtime, change):
    row = connection("google_analytics")
    if change == "deleted":
        row = None
    elif change == "disabled":
        row.status = "disabled"
    elif change == "recreated":
        row.id += 1
    elif change == "revision":
        row.snapshot_revision = "new-revision"
    elif change == "config":
        row.public_config = {"property_id": "999"}
    else:
        row.credentials_fingerprint = "new-credentials"
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: row)))
    async def rotate(credentials):
        credentials["access_token"] = "rotated-secret"
        return "rotated-secret"
    monkeypatch.setattr(sources, "google_access_token", rotate)
    persist = AsyncMock()
    fetch = AsyncMock()
    monkeypatch.setattr(sources.AnalyticsConnectionService, "persist_refreshed_credentials", persist)
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", fetch)
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(session, SCOPE, "google_analytics", START, END)
    assert error.value.code == "source_changed"
    persist.assert_not_awaited()
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,configured", [(TenantScope(2, 7), True), (TenantScope(2, 7, is_system=True), False)])
async def test_environment_metrika_never_crosses_system_scope_or_exact_storefront(monkeypatch, runtime, scope, configured):
    runtime.return_value = None
    monkeypatch.setattr(sources.settings, "DASHBOARD_METRIKA_OAUTH_TOKEN", "environment-secret")
    monkeypatch.setattr(sources.settings, "DASHBOARD_METRIKA_STOREFRONT_COUNTERS_JSON", '{"2:7":"123"}' if configured else '{"2:8":"123"}')
    fetch = AsyncMock()
    monkeypatch.setattr(sources.YandexMetrikaMarketingProvider, "_fetch_snapshot", fetch)
    with pytest.raises(sources.SourceFetchError):
        await sources.fetch_source(object(), scope, "yandex_metrika", START, END)
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_environment_metrika_works_for_exact_system_scope_only(monkeypatch, runtime):
    from services.dashboard_marketing import MarketingSnapshot
    runtime.return_value = None
    monkeypatch.setattr(sources.settings, "DASHBOARD_METRIKA_OAUTH_TOKEN", "environment-secret")
    monkeypatch.setattr(sources.settings, "DASHBOARD_METRIKA_STOREFRONT_COUNTERS_JSON", '{"2:7":"123"}')
    fetch = AsyncMock(return_value=MarketingSnapshot(status="fresh", visits=0, updated_at=datetime.now(timezone.utc)))
    monkeypatch.setattr(sources.YandexMetrikaMarketingProvider, "_fetch_snapshot", fetch)
    result = await sources.fetch_source(object(), TenantScope(2, 7, is_system=True), "yandex_metrika", START, END)
    assert result["marketing"]["visits"] == 0
    assert fetch.await_args.kwargs["counter_id"] == "123"


@pytest.mark.asyncio
async def test_disabled_connection_does_not_fall_back_to_environment(monkeypatch, runtime):
    runtime.return_value.status = "disabled"
    monkeypatch.setattr(sources.settings, "DASHBOARD_METRIKA_OAUTH_TOKEN", "environment-secret")
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(object(), TenantScope(2, 7, is_system=True), "yandex_metrika", START, END)
    assert error.value.code == "source_unconfigured"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"totals": []}, {"totals": ["bad"]}, {"totals": [-1]}, {"totals": [float("nan")]}])
async def test_metrika_malformed_success_cannot_become_zero(payload):
    response = httpx.Response(
        200, content=json.dumps(payload).encode(),
        request=httpx.Request("GET", "https://provider.test"),
    )
    with pytest.raises(sources.SourceFetchError):
        await sources._validate_metrika_response(response)


@pytest.mark.asyncio
async def test_cancellation_is_propagated_not_converted_to_failure(monkeypatch, runtime):
    monkeypatch.setattr(sources, "google_access_token", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await sources.fetch_source(object(), SCOPE, "google_analytics", START, END)


@pytest.mark.asyncio
async def test_unchanged_oauth_does_not_write_connection(monkeypatch, runtime):
    persist = AsyncMock()
    monkeypatch.setattr(sources.AnalyticsConnectionService, "persist_refreshed_credentials", persist)
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", AsyncMock(return_value=GoogleAnalyticsSnapshot(0, 0, 0.0, 0.0, {})))
    result = await sources.fetch_source(object(), SCOPE, "google_analytics", START, END)
    assert result["marketing"]["visits"] == 0
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreadable_credentials_fail_without_external_request(monkeypatch, runtime):
    monkeypatch.setattr(sources.AnalyticsCredentialCipher, "decrypt", Mock(side_effect=ValueError("secret-ciphertext")))
    fetch = AsyncMock()
    monkeypatch.setattr(sources.GoogleAnalyticsProvider, "fetch", fetch)
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(object(), SCOPE, "google_analytics", START, END)
    assert str(error.value) == "credentials_unavailable"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,start,end,code", [
    ("unsupported", START, END, "unsupported_provider"),
    ("google_analytics", END, START, "invalid_period"),
])
async def test_invalid_request_is_rejected_before_loading_credentials(runtime, provider, start, end, code):
    with pytest.raises(sources.SourceFetchError) as error:
        await sources.fetch_source(object(), SCOPE, provider, start, end)
    assert error.value.code == code
    runtime.assert_not_awaited()
