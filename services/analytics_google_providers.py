"""Google Analytics, Search Console and Ads adapters with isolated OAuth handling."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlparse

import httpx
from google_auth_oauthlib.flow import Flow

from services.analytics_provider_types import (
    AdvertisingSnapshot,
    AnalyticsProviderError,
    GoogleOAuthCredentialPayload,
    SearchQueryRow,
    SearchDemandProviderSnapshot,
)

GOOGLE_ANALYTICS_SCOPES = ("https://www.googleapis.com/auth/analytics.readonly",)
GOOGLE_SEARCH_CONSOLE_SCOPES = ("https://www.googleapis.com/auth/webmasters.readonly",)
GOOGLE_ADS_SCOPES = ("https://www.googleapis.com/auth/adwords",)
GOOGLE_MARKETING_SCOPES = GOOGLE_ANALYTICS_SCOPES + GOOGLE_SEARCH_CONSOLE_SCOPES + GOOGLE_ADS_SCOPES
_ClientFactory = Callable[[], httpx.AsyncClient]


def _factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, trust_env=False)


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _error(response: httpx.Response, provider: str) -> AnalyticsProviderError:
    if response.status_code in {401, 403}:
        return AnalyticsProviderError(f"{provider}_access_denied", "Provider access was denied")
    return AnalyticsProviderError(
        f"{provider}_unavailable",
        "Provider is temporarily unavailable",
        retryable=response.status_code == 429 or response.status_code >= 500,
    )


def _micros(value: Any) -> float:
    return round(float(value or 0) / 1_000_000, 2)


class GoogleOAuthProvider:
    """Build/exchange/refresh credentials without coupling them to any database model."""

    @staticmethod
    def build_authorization_url(*, client_secret_path: str | Path, redirect_uri: str, state: str, scopes: tuple[str, ...] = GOOGLE_MARKETING_SCOPES) -> str:
        flow = Flow.from_client_secrets_file(str(client_secret_path), scopes=scopes, redirect_uri=redirect_uri)
        url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
        return url

    @staticmethod
    def exchange_authorization_code(*, client_secret_path: str | Path, redirect_uri: str, code: str, scopes: tuple[str, ...] = GOOGLE_MARKETING_SCOPES, flow_factory: Callable[..., Flow] = Flow.from_client_secrets_file) -> GoogleOAuthCredentialPayload:
        try:
            flow = flow_factory(str(client_secret_path), scopes=scopes, redirect_uri=redirect_uri)
            flow.fetch_token(code=code)
            credentials = flow.credentials
            return GoogleOAuthCredentialPayload(
                access_token=credentials.token or "",
                refresh_token=credentials.refresh_token,
                client_id=credentials.client_id or "",
                client_secret=credentials.client_secret or "",
                token_uri=credentials.token_uri or "https://oauth2.googleapis.com/token",
                expiry=credentials.expiry,
                scopes=tuple(credentials.scopes or scopes),
            )
        except Exception as exc:
            raise AnalyticsProviderError("google_oauth_exchange_failed", "Google authorization code exchange failed") from exc

    def __init__(self, *, client_factory: _ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _factory

    async def refresh(self, credentials: GoogleOAuthCredentialPayload) -> GoogleOAuthCredentialPayload:
        if not credentials.refresh_token:
            raise AnalyticsProviderError("google_refresh_token_missing", "Google connection needs to be connected again")
        async with self._client_factory() as client:
            response = await client.post(credentials.token_uri, data={"grant_type": "refresh_token", "refresh_token": credentials.refresh_token, "client_id": credentials.client_id, "client_secret": credentials.client_secret})
        if response.status_code != 200:
            raise _error(response, "google_oauth")
        try:
            data = response.json()
            return GoogleOAuthCredentialPayload(
                access_token=str(data["access_token"]), refresh_token=credentials.refresh_token,
                client_id=credentials.client_id, client_secret=credentials.client_secret, token_uri=credentials.token_uri,
                expiry=datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600))),
                scopes=tuple(str(data.get("scope", "")).split()) or credentials.scopes,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalyticsProviderError("google_oauth_invalid_response", "Google returned an invalid token response") from exc

    async def access_token(self, credentials: Mapping[str, Any]) -> str:
        """Return a usable token; callers persist ``last_refreshed_payload`` if set."""
        parsed = GoogleOAuthCredentialPayload.from_payload(credentials)
        now = datetime.now(timezone.utc)
        if parsed.access_token and (parsed.expiry is None or parsed.expiry > now + timedelta(seconds=60)):
            self.last_refreshed_payload: dict[str, Any] | None = None
            return parsed.access_token
        refreshed = await self.refresh(parsed)
        self.last_refreshed_payload = refreshed.to_payload()
        return refreshed.access_token


def _provider_scopes(provider: str) -> tuple[str, ...]:
    return {
        "google_analytics": GOOGLE_ANALYTICS_SCOPES,
        "google_search_console": GOOGLE_SEARCH_CONSOLE_SCOPES,
        "google_ads": GOOGLE_ADS_SCOPES,
    }.get(provider, GOOGLE_MARKETING_SCOPES)


def build_authorization_url(
    provider: str, redirect_uri: str, state: str, *, client_secret_path: str | Path = "client_secret.json"
) -> str:
    return GoogleOAuthProvider.build_authorization_url(
        client_secret_path=client_secret_path, redirect_uri=redirect_uri, state=state, scopes=_provider_scopes(provider)
    )


def exchange_code(
    provider: str, redirect_uri: str, code: str, *, client_secret_path: str | Path = "client_secret.json", flow_factory: Callable[..., Flow] = Flow.from_client_secrets_file
) -> dict[str, Any]:
    payload = GoogleOAuthProvider.exchange_authorization_code(
        client_secret_path=client_secret_path, redirect_uri=redirect_uri, code=code,
        scopes=_provider_scopes(provider), flow_factory=flow_factory,
    ).to_payload()
    payload.pop("client_id", None)
    payload.pop("client_secret", None)
    return payload


def _oauth_client_config(client_secret_path: str | Path) -> dict[str, str]:
    try:
        raw = json.loads(Path(client_secret_path).read_text(encoding="utf-8"))
        configured = raw.get("web") or raw.get("installed")
        if not isinstance(configured, Mapping):
            raise TypeError("client configuration")
        client_id = str(configured["client_id"])
        client_secret = str(configured["client_secret"])
        token_uri = str(
            configured.get("token_uri") or "https://oauth2.googleapis.com/token"
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AnalyticsProviderError(
            "google_oauth_system_not_configured",
            "Google OAuth is not configured on the server",
        ) from exc
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "token_uri": token_uri,
    }


async def access_token(
    credentials: Mapping[str, Any],
    *,
    client_factory: _ClientFactory | None = None,
    client_secret_path: str | Path = "client_secret.json",
) -> str:
    """Return a usable token and update a mutable payload after a refresh.

    This keeps the public API a simple ``-> str`` while allowing the connection
    service to re-encrypt the same payload object after this call.
    """
    runtime_credentials = dict(credentials)
    if not runtime_credentials.get("client_id") or not runtime_credentials.get(
        "client_secret"
    ):
        runtime_credentials.update(_oauth_client_config(client_secret_path))
    provider = GoogleOAuthProvider(client_factory=client_factory)
    token = await provider.access_token(runtime_credentials)
    if isinstance(credentials, dict) and provider.last_refreshed_payload:
        persisted = dict(provider.last_refreshed_payload)
        persisted.pop("client_id", None)
        persisted.pop("client_secret", None)
        credentials.clear()
        credentials.update(persisted)
    return token


class GoogleAnalyticsProvider:
    BASE_URL = "https://analyticsdata.googleapis.com/v1beta"
    scopes = GOOGLE_ANALYTICS_SCOPES
    def __init__(self, *, client_factory: _ClientFactory | None = None) -> None: self._client_factory = client_factory or _factory

    async def fetch_sessions_by_source(self, *, access_token: str, property_id: str, period_start: date, period_end: date) -> dict[str, int]:
        body = {"dateRanges": [{"startDate": period_start.isoformat(), "endDate": period_end.isoformat()}], "dimensions": [{"name": "sessionSourceMedium"}], "metrics": [{"name": "sessions"}]}
        async with self._client_factory() as client:
            response = await client.post(f"{self.BASE_URL}/properties/{property_id}:runReport", headers=_headers(access_token), json=body)
        if response.status_code != 200: raise _error(response, "google_analytics")
        try:
            return {str(row["dimensionValues"][0].get("value") or "(not set)"): int(row["metricValues"][0].get("value") or 0) for row in response.json().get("rows", [])}
        except (IndexError, KeyError, TypeError, ValueError) as exc: raise AnalyticsProviderError("google_analytics_invalid_response", "Provider returned an invalid response") from exc

    async def verify(self, access_token: str, public_config: Mapping[str, Any], developer_token: str | None = None) -> dict[str, str]:
        property_id = str(public_config.get("property_id") or "")
        if not property_id:
            raise AnalyticsProviderError("google_analytics_config_invalid", "GA4 property ID is required")
        today = date.today()
        await self.fetch_sessions_by_source(access_token=access_token, property_id=property_id, period_start=today, period_end=today)
        return {"property_id": property_id}

    async def fetch(self, access_token: str, public_config: Mapping[str, Any], period_start: date, period_end: date) -> dict[str, int]:
        return await self.fetch_sessions_by_source(access_token=access_token, property_id=str(public_config["property_id"]), period_start=period_start, period_end=period_end)


class GoogleSearchConsoleProvider:
    BASE_URL = "https://www.googleapis.com/webmasters/v3"
    scopes = GOOGLE_SEARCH_CONSOLE_SCOPES
    def __init__(self, *, client_factory: _ClientFactory | None = None) -> None: self._client_factory = client_factory or _factory

    async def resolve_property(self, *, access_token: str, primary_hostname: str) -> str:
        expected = primary_hostname.strip().lower().rstrip(".")
        if not expected:
            raise AnalyticsProviderError(
                "google_search_console_config_invalid",
                "Primary hostname is required",
            )
        async with self._client_factory() as client:
            response = await client.get(f"{self.BASE_URL}/sites", headers=_headers(access_token))
        if response.status_code != 200:
            raise _error(response, "google_search_console")
        try:
            entries = response.json().get("siteEntry", [])
        except ValueError as exc:
            raise AnalyticsProviderError(
                "google_search_console_invalid_response",
                "Provider returned an invalid response",
            ) from exc
        domain_property = f"sc-domain:{expected}"
        url_matches: list[str] = []
        domain_match: str | None = None
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            permission = str(entry.get("permissionLevel") or "")
            if permission in {"", "siteUnverifiedUser"}:
                continue
            site_url = str(entry.get("siteUrl") or "")
            if site_url == domain_property:
                domain_match = site_url
                continue
            parsed = urlparse(site_url)
            if (parsed.hostname or "").lower().rstrip(".") == expected:
                url_matches.append(site_url)
        if url_matches:
            return sorted(url_matches, key=lambda value: (not value.startswith("https://"), len(value)))[0]
        if domain_match:
            return domain_match
        raise AnalyticsProviderError(
            "google_search_console_property_not_verified",
            "The exact storefront domain is not verified in Search Console",
        )

    async def verify_property(self, *, access_token: str, site_property: str) -> None:
        encoded = quote(site_property, safe="")
        async with self._client_factory() as client:
            response = await client.get(f"{self.BASE_URL}/sites/{encoded}", headers=_headers(access_token))
        if response.status_code != 200: raise _error(response, "google_search_console")

    async def verify(self, access_token: str, public_config: Mapping[str, Any], developer_token: str | None = None) -> dict[str, str]:
        site_property = str(public_config.get("site_property") or "")
        if not site_property and public_config.get("primary_hostname"):
            site_property = await self.resolve_property(
                access_token=access_token,
                primary_hostname=str(public_config["primary_hostname"]),
            )
        if not site_property:
            raise AnalyticsProviderError("google_search_console_config_invalid", "Search Console property is required")
        await self.verify_property(access_token=access_token, site_property=site_property)
        return {"site_property": site_property}

    async def fetch_query_rows(self, *, access_token: str, site_property: str, period_start: date, period_end: date, limit: int = 100) -> tuple[SearchQueryRow, ...]:
        encoded = quote(site_property, safe="")
        body = {"startDate": period_start.isoformat(), "endDate": period_end.isoformat(), "dimensions": ["query"], "rowLimit": min(max(limit, 1), 25000)}
        async with self._client_factory() as client:
            response = await client.post(f"{self.BASE_URL}/sites/{encoded}/searchAnalytics/query", headers=_headers(access_token), json=body)
        if response.status_code != 200: raise _error(response, "google_search_console")
        try:
            return tuple(SearchQueryRow(query=str(row["keys"][0]), clicks=int(row.get("clicks", 0)), impressions=int(row.get("impressions", 0)), ctr=round(float(row.get("ctr", 0)) * 100, 2), position=round(float(row["position"]), 2) if row.get("position") is not None else None) for row in response.json().get("rows", []))
        except (IndexError, KeyError, TypeError, ValueError) as exc: raise AnalyticsProviderError("google_search_console_invalid_response", "Provider returned an invalid response") from exc

    async def fetch(self, access_token: str, public_config: Mapping[str, Any], period_start: date, period_end: date, *, limit: int = 100) -> SearchDemandProviderSnapshot:
        rows = await self.fetch_query_rows(access_token=access_token, site_property=str(public_config["site_property"]), period_start=period_start, period_end=period_end, limit=limit)
        return SearchDemandProviderSnapshot("google_search_console", rows)


class GoogleAdsProvider:
    BASE_URL = "https://googleads.googleapis.com/v25"
    scopes = GOOGLE_ADS_SCOPES
    def __init__(self, *, developer_token: str, client_factory: _ClientFactory | None = None) -> None:
        self._developer_token, self._client_factory = developer_token, client_factory or _factory

    async def fetch_advertising_snapshot(self, *, access_token: str, customer_id: str, period_start: date, period_end: date, login_customer_id: str | None = None) -> AdvertisingSnapshot:
        headers = {**_headers(access_token), "developer-token": self._developer_token}
        if login_customer_id: headers["login-customer-id"] = login_customer_id.replace("-", "")
        query = "SELECT customer.currency_code, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions FROM customer WHERE segments.date BETWEEN '" + period_start.isoformat() + "' AND '" + period_end.isoformat() + "'"
        async with self._client_factory() as client:
            response = await client.post(f"{self.BASE_URL}/customers/{customer_id.replace('-', '')}/googleAds:searchStream", headers=headers, json={"query": query})
        if response.status_code != 200: raise _error(response, "google_ads")
        try:
            rows = [row for batch in response.json() for row in batch.get("results", [])]
            currencies = {
                str(row.get("customer", {}).get("currencyCode") or "")
                for row in rows
                if row.get("customer", {}).get("currencyCode")
            }
            return AdvertisingSnapshot(
                "google_ads",
                period_start,
                period_end,
                sum(int(row.get("metrics", {}).get("impressions", 0)) for row in rows),
                sum(int(row.get("metrics", {}).get("clicks", 0)) for row in rows),
                round(sum(_micros(row.get("metrics", {}).get("costMicros")) for row in rows), 2),
                round(sum(float(row.get("metrics", {}).get("conversions", 0)) for row in rows), 2),
                next(iter(currencies)) if len(currencies) == 1 else None,
            )
        except (TypeError, ValueError) as exc: raise AnalyticsProviderError("google_ads_invalid_response", "Provider returned an invalid response") from exc

    async def verify(self, access_token: str, public_config: Mapping[str, Any], developer_token: str | None = None) -> dict[str, str]:
        customer_id = str(public_config.get("customer_id") or "")
        if not customer_id:
            raise AnalyticsProviderError("google_ads_config_invalid", "Google Ads customer ID is required")
        if developer_token and developer_token != self._developer_token:
            raise AnalyticsProviderError("google_ads_developer_token_mismatch", "Google Ads system configuration is invalid")
        today = date.today()
        snapshot = await self.fetch_advertising_snapshot(access_token=access_token, customer_id=customer_id, period_start=today, period_end=today, login_customer_id=str(public_config.get("login_customer_id") or "") or None)
        return {
            "customer_id": customer_id,
            "login_customer_id": str(public_config.get("login_customer_id") or ""),
            "currency": snapshot.currency or "",
        }

    async def fetch(self, access_token: str, public_config: Mapping[str, Any], period_start: date, period_end: date) -> AdvertisingSnapshot:
        return await self.fetch_advertising_snapshot(access_token=access_token, customer_id=str(public_config["customer_id"]), period_start=period_start, period_end=period_end, login_customer_id=str(public_config.get("login_customer_id") or "") or None)
