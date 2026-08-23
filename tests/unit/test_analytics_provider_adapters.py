from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from services.analytics_google_providers import (
    GoogleAdsProvider,
    GoogleAnalyticsProvider,
    GoogleOAuthProvider,
    GoogleSearchConsoleProvider,
    access_token,
)
from services.analytics_provider_types import GoogleOAuthCredentialPayload
from services.analytics_yandex_providers import YandexDirectProvider, YandexWebmasterProvider


def _client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_google_analytics_fetches_summary_without_summing_unique_users():
    def handler(request: httpx.Request):
        body = request.read().decode()
        if "sessionSourceMedium" in body:
            return httpx.Response(200, json={"rows": [
                {"dimensionValues": [{"value": "google / organic"}], "metricValues": [{"value": "7"}]},
                {"dimensionValues": [{"value": "direct / none"}], "metricValues": [{"value": "3"}]},
            ]})
        assert '"activeUsers"' in body
        assert '"engagementRate"' in body
        return httpx.Response(200, json={"rows": [{"metricValues": [
            {"value": "10"}, {"value": "8"}, {"value": "0.625"}, {"value": "93.4"},
        ]}]})

    snapshot = await GoogleAnalyticsProvider(client_factory=_client(handler)).fetch(
        "google-access",
        {"property_id": "123456"},
        date(2026, 8, 1),
        date(2026, 8, 2),
    )

    assert snapshot.sessions == 10
    assert snapshot.active_users == 8
    assert snapshot.engagement_rate == 62.5
    assert snapshot.average_session_duration_seconds == 93.4
    assert snapshot.sources == {"google / organic": 7, "direct / none": 3}


@pytest.mark.asyncio
async def test_google_analytics_verifies_an_empty_property():
    provider = GoogleAnalyticsProvider(
        client_factory=_client(lambda _request: httpx.Response(200, json={}))
    )

    assert await provider.verify("google-access", {"property_id": "123456"}) == {
        "property_id": "123456"
    }


@pytest.mark.asyncio
async def test_yandex_direct_verifies_client_login_and_parses_tsv_report():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(200, json={"result": {"Campaigns": [{"Id": 7}]}})
        return httpx.Response(200, text="Impressions\tClicks\tCost\n100\t5\t12.50\n200\t10\t25.25\n")

    provider = YandexDirectProvider(client_factory=_client(handler))
    verified = await provider.verify("secret-token", "agency-client")
    snapshot = await provider.fetch("secret-token", {"client_login": "agency-client"}, date(2026, 8, 1), date(2026, 8, 2))

    assert verified == {
        "client_login": "agency-client",
        "campaigns_checked": 1,
        "currency": None,
    }
    assert snapshot.impressions == 300 and snapshot.clicks == 15 and snapshot.spend == 37.75
    assert snapshot.ctr == 5.0
    assert all(request.headers["authorization"] == "Bearer secret-token" for request in seen)
    assert all(request.headers["client-login"] == "agency-client" for request in seen)


@pytest.mark.asyncio
async def test_yandex_direct_retries_same_asynchronous_report_request():
    attempts = 0

    def handler(_request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(202)
        return httpx.Response(
            200,
            text="Impressions\tClicks\tCost\tConversions\n100\t5\t12.50\t1\n",
        )

    snapshot = await YandexDirectProvider(
        client_factory=_client(handler)
    ).fetch_advertising_snapshot(
        oauth_token="secret-token",
        client_login=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 2),
        currency="BYN",
    )

    assert attempts == 3
    assert snapshot.spend == 12.5
    assert snapshot.currency == "BYN"


@pytest.mark.asyncio
async def test_yandex_webmaster_binds_exact_primary_hostname_and_fetches_query_demand():
    def handler(request: httpx.Request):
        if request.url.path == "/v4/user":
            return httpx.Response(200, json={"user_id": 42})
        if request.url.path.endswith("/hosts"):
            return httpx.Response(200, json={"hosts": [
                {"host_id": "https:www.mvn.by:443", "ascii_host_url": "https://www.mvn.by/", "verified": True},
                {"host_id": "https:mvn.by:443", "ascii_host_url": "https://mvn.by/", "verified": True},
            ]})
        assert request.url.params["order_by"] == "TOTAL_CLICKS"
        return httpx.Response(200, json={"queries": [{"query_text": "купить кондиционер", "TOTAL_CLICKS": 8, "TOTAL_SHOWS": 100, "AVG_SHOW_POSITION": 3.4}]})

    provider = YandexWebmasterProvider(client_factory=_client(handler))
    config = await provider.verify("webmaster-secret", "mvn.by")
    snapshot = await provider.fetch("webmaster-secret", config)

    assert config == {"user_id": "42", "host_id": "https:mvn.by:443", "site_url": "https://mvn.by/"}
    assert snapshot.rows[0].query == "купить кондиционер"
    assert snapshot.rows[0].ctr == 8.0 and snapshot.rows[0].position == 3.4


@pytest.mark.asyncio
async def test_google_oauth_refresh_keeps_secret_out_of_error_and_marks_payload_for_persistence():
    def handler(request: httpx.Request):
        assert request.url == httpx.URL("https://oauth2.googleapis.com/token")
        assert request.content and b"refresh-secret" in request.content
        return httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600, "scope": "scope-a"})

    provider = GoogleOAuthProvider(client_factory=_client(handler))
    token = await provider.access_token(GoogleOAuthCredentialPayload(
        access_token="expired", refresh_token="refresh-secret", client_id="client-id", client_secret="client-secret",
        token_uri="https://oauth2.googleapis.com/token", expiry=datetime.now(timezone.utc) - timedelta(seconds=1), scopes=("scope-a",),
    ).to_payload())

    assert token == "fresh-access"
    assert provider.last_refreshed_payload is not None
    assert provider.last_refreshed_payload["refresh_token"] == "refresh-secret"


@pytest.mark.asyncio
async def test_google_oauth_runtime_uses_system_client_secret_without_persisting_it(tmp_path):
    client_config = tmp_path / "google-client.json"
    client_config.write_text(
        '{"web":{"client_id":"system-client","client_secret":"system-secret",'
        '"token_uri":"https://oauth2.googleapis.com/token"}}',
        encoding="utf-8",
    )

    def handler(request: httpx.Request):
        assert b"system-client" in request.content
        assert b"system-secret" in request.content
        return httpx.Response(
            200,
            json={"access_token": "fresh-access", "expires_in": 3600},
        )

    credentials = GoogleOAuthCredentialPayload(
        access_token="expired",
        refresh_token="storefront-refresh",
        client_id="unused",
        client_secret="unused",
        token_uri="https://oauth2.googleapis.com/token",
        expiry=datetime.now(timezone.utc) - timedelta(seconds=1),
        scopes=("scope-a",),
    ).to_payload()
    credentials.pop("client_id")
    credentials.pop("client_secret")

    token = await access_token(
        credentials,
        client_factory=_client(handler),
        client_secret_path=client_config,
    )

    assert token == "fresh-access"
    assert credentials["refresh_token"] == "storefront-refresh"
    assert "client_id" not in credentials
    assert "client_secret" not in credentials


@pytest.mark.asyncio
async def test_search_console_uses_exact_property_and_maps_query_rows():
    def handler(request: httpx.Request):
        assert "%3A" in str(request.url)
        assert request.headers["authorization"] == "Bearer google-access"
        return httpx.Response(200, json={"rows": [{"keys": ["кондиционер витебск"], "clicks": 5, "impressions": 50, "ctr": 0.1, "position": 2.1}]})

    provider = GoogleSearchConsoleProvider(client_factory=_client(handler))
    snapshot = await provider.fetch("google-access", {"site_property": "sc-domain:mvn.by"}, date(2026, 8, 1), date(2026, 8, 2))

    assert snapshot.rows == (snapshot.rows[0],)
    assert snapshot.rows[0].query == "кондиционер витебск"
    assert snapshot.rows[0].ctr == 10.0


@pytest.mark.asyncio
async def test_google_ads_uses_system_developer_token_and_target_customer():
    def handler(request: httpx.Request):
        assert request.headers["developer-token"] == "system-developer-token"
        assert request.url.path == "/v25/customers/1234567890/googleAds:searchStream"
        return httpx.Response(200, json=[{"results": [{"metrics": {"impressions": "25", "clicks": "3", "costMicros": "4500000"}}]}])

    provider = GoogleAdsProvider(developer_token="system-developer-token", client_factory=_client(handler))
    config = await provider.verify("google-access", {"customer_id": "123-456-7890"})
    snapshot = await provider.fetch("google-access", config, date(2026, 8, 1), date(2026, 8, 2))

    assert snapshot.impressions == 25 and snapshot.clicks == 3 and snapshot.spend == 4.5
