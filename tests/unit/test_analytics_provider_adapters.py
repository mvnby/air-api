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
from services.analytics_provider_types import (
    AnalyticsProviderError,
    GoogleOAuthCredentialPayload,
)
from services.analytics_yandex_providers import YandexDirectProvider, YandexWebmasterProvider


def _client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_google_oauth_keeps_provider_scopes_isolated(monkeypatch):
    seen = {}

    class _FlowStub:
        def authorization_url(self, **kwargs):
            seen.update(kwargs)
            return "https://accounts.google.com/o/oauth2/auth", "state"

    def from_client_secrets_file(path, *, scopes, redirect_uri):
        seen.update(path=path, scopes=scopes, redirect_uri=redirect_uri)
        return _FlowStub()

    monkeypatch.setattr(
        "services.analytics_google_providers.Flow.from_client_secrets_file",
        from_client_secrets_file,
    )

    url = GoogleOAuthProvider.build_authorization_url(
        client_secret_path="google-client.json",
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
        state="one-time-state",
        scopes=("https://www.googleapis.com/auth/analytics.readonly",),
    )

    assert url == "https://accounts.google.com/o/oauth2/auth"
    assert seen["scopes"] == (
        "https://www.googleapis.com/auth/analytics.readonly",
    )
    assert seen["access_type"] == "offline"
    assert seen["prompt"] == "consent"
    assert seen["state"] == "one-time-state"
    assert seen["include_granted_scopes"] == "true"


def test_google_oauth_accepts_incremental_scope_superset():
    required = "https://www.googleapis.com/auth/analytics.readonly"
    extra = "https://www.googleapis.com/auth/webmasters.readonly"

    class _FlowStub:
        oauth2session = type("OAuthSession", (), {"token": {}})()

        def fetch_token(self, *, code):
            assert code == "one-time-code"
            warning = Warning("scope changed")
            warning.new_scope = [required, extra]
            warning.token = {
                "access_token": "temporary-access",
                "refresh_token": "offline-refresh",
                "token_type": "Bearer",
                "scope": [required, extra],
            }
            raise warning

        @property
        def credentials(self):
            token = self.oauth2session.token
            return type(
                "Credentials",
                (),
                {
                    "token": token["access_token"],
                    "refresh_token": token["refresh_token"],
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "expiry": None,
                    # google-auth-oauthlib reports the scopes configured on the
                    # Flow here, not necessarily the actual granted superset.
                    "scopes": [required],
                },
            )()

    payload = GoogleOAuthProvider.exchange_authorization_code(
        client_secret_path="google-client.json",
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
        code="one-time-code",
        scopes=(required,),
        flow_factory=lambda *_args, **_kwargs: _FlowStub(),
    )

    assert payload.access_token == "temporary-access"
    assert payload.refresh_token == "offline-refresh"
    assert set(payload.scopes) == {required, extra}


def test_google_oauth_payload_normalizes_naive_expiry_to_utc():
    payload = GoogleOAuthCredentialPayload.from_payload(
        {
            "access_token": "token",
            "refresh_token": "refresh",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "expiry": "2026-08-23T15:22:00",
            "scopes": ["scope-a"],
        }
    )

    assert payload.expiry == datetime(2026, 8, 23, 15, 22, tzinfo=timezone.utc)


def test_google_oauth_payload_preserves_explicit_expiry_offset():
    payload = GoogleOAuthCredentialPayload.from_payload(
        {
            "access_token": "token",
            "refresh_token": "refresh",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "expiry": "2026-08-23T18:22:00+03:00",
            "scopes": ["scope-a"],
        }
    )

    assert payload.expiry == datetime.fromisoformat("2026-08-23T18:22:00+03:00")


@pytest.mark.parametrize(
    ("granted_scopes", "refresh_token", "expected_code"),
    [
        (
            ("https://www.googleapis.com/auth/webmasters.readonly",),
            "offline-refresh",
            "google_oauth_scope_mismatch",
        ),
        (
            ("https://www.googleapis.com/auth/analytics.readonly",),
            None,
            "google_oauth_refresh_token_missing",
        ),
    ],
)
def test_google_oauth_rejects_missing_required_scope_or_refresh_token(
    granted_scopes, refresh_token, expected_code
):
    required = "https://www.googleapis.com/auth/analytics.readonly"

    class _FlowStub:
        oauth2session = type("OAuthSession", (), {"token": {}})()

        def fetch_token(self, *, code):
            warning = Warning("scope changed")
            warning.new_scope = list(granted_scopes)
            warning.token = {
                "access_token": "temporary-access",
                "refresh_token": refresh_token,
                "scope": list(granted_scopes),
            }
            raise warning

        @property
        def credentials(self):
            token = self.oauth2session.token
            return type(
                "Credentials",
                (),
                {
                    "token": token.get("access_token"),
                    "refresh_token": token.get("refresh_token"),
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "expiry": None,
                    "scopes": token.get("scope"),
                },
            )()

    with pytest.raises(AnalyticsProviderError) as error:
        GoogleOAuthProvider.exchange_authorization_code(
            client_secret_path="google-client.json",
            redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
            code="one-time-code",
            scopes=(required,),
            flow_factory=lambda *_args, **_kwargs: _FlowStub(),
        )

    assert error.value.code == expected_code


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
async def test_google_oauth_access_token_accepts_naive_future_expiry_without_refresh():
    provider = GoogleOAuthProvider(
        client_factory=lambda: (_ for _ in ()).throw(
            AssertionError("refresh should not run for a still-valid token")
        )
    )

    token = await provider.access_token(
        GoogleOAuthCredentialPayload(
            access_token="still-valid",
            refresh_token="refresh-secret",
            client_id="client-id",
            client_secret="client-secret",
            token_uri="https://oauth2.googleapis.com/token",
            expiry=datetime.now() + timedelta(minutes=5),
            scopes=("scope-a",),
        ).to_payload()
    )

    assert token == "still-valid"
    assert provider.last_refreshed_payload is None


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
