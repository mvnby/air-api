"""Yandex Direct and Webmaster adapters using their documented HTTPS APIs."""

from __future__ import annotations

import asyncio
import csv
from datetime import date
from io import StringIO
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx

from services.analytics_provider_types import (
    AdvertisingSnapshot,
    AnalyticsProviderError,
    SearchQueryRow,
    SearchDemandProviderSnapshot,
)

_ClientFactory = Callable[[], httpx.AsyncClient]


def _factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, trust_env=False)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _oauth(token: str) -> dict[str, str]:
    return {"Authorization": f"OAuth {token}"}


def _number(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(str(value).replace(" ", "").replace(",", "."))


def _provider_error(response: httpx.Response, *, provider: str) -> AnalyticsProviderError:
    if response.status_code in {401, 403}:
        return AnalyticsProviderError(f"{provider}_access_denied", "Provider access was denied")
    return AnalyticsProviderError(
        f"{provider}_unavailable",
        "Provider is temporarily unavailable",
        retryable=response.status_code == 429 or response.status_code >= 500,
    )


class YandexDirectProvider:
    CAMPAIGNS_URL = "https://api.direct.yandex.com/json/v501/campaigns"
    REPORTS_URL = "https://api.direct.yandex.com/json/v501/reports"

    def __init__(self, *, client_factory: _ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _factory

    @staticmethod
    def _headers(token: str, client_login: str | None = None) -> dict[str, str]:
        headers = {**_bearer(token), "Accept-Language": "ru"}
        if client_login:
            headers["Client-Login"] = client_login
        return headers

    async def verify(self, oauth_token: str, client_login: str | None = None) -> dict[str, str | int | None]:
        body = {"method": "get", "params": {"SelectionCriteria": {}, "FieldNames": ["Id", "Name", "Currency"], "Page": {"Limit": 1, "Offset": 0}}}
        async with self._client_factory() as client:
            response = await client.post(self.CAMPAIGNS_URL, headers=self._headers(oauth_token, client_login), json=body)
        if response.status_code != 200:
            raise _provider_error(response, provider="yandex_direct")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AnalyticsProviderError("yandex_direct_invalid_response", "Provider returned an invalid response") from exc
        if not isinstance(payload, Mapping) or "error" in payload:
            raise AnalyticsProviderError("yandex_direct_access_denied", "Provider access was denied")
        campaigns = payload.get("result", {}).get("Campaigns", []) if isinstance(payload.get("result"), Mapping) else []
        currencies = {
            str(campaign.get("Currency") or "")
            for campaign in campaigns
            if isinstance(campaign, Mapping) and campaign.get("Currency")
        }
        return {
            "client_login": client_login,
            "campaigns_checked": len(campaigns) if isinstance(campaigns, list) else 0,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        }

    async def fetch_advertising_snapshot(
        self, *, oauth_token: str, client_login: str | None, period_start: date, period_end: date,
        currency: str | None = None,
    ) -> AdvertisingSnapshot:
        body = {
            "params": {
                "SelectionCriteria": {"DateFrom": period_start.isoformat(), "DateTo": period_end.isoformat()},
                "FieldNames": ["CampaignId", "Impressions", "Clicks", "Cost", "Conversions"],
                "ReportName": f"mvn_dashboard_{period_start.isoformat()}_{period_end.isoformat()}",
                "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
                "DateRangeType": "CUSTOM_DATE",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        headers = {
            **self._headers(oauth_token, client_login),
            "skipReportHeader": "true",
            "skipColumnHeader": "false",
            "skipReportSummary": "true",
            "returnMoneyInMicros": "false",
            "processingMode": "auto",
        }
        async with self._client_factory() as client:
            for attempt in range(3):
                response = await client.post(self.REPORTS_URL, headers=headers, json=body)
                if response.status_code not in {201, 202}:
                    break
                if attempt < 2:
                    await asyncio.sleep(0.5)
        if response.status_code in {201, 202}:
            raise AnalyticsProviderError(
                "yandex_direct_report_pending",
                "Advertising report is being prepared",
                retryable=True,
            )
        if response.status_code != 200:
            raise _provider_error(response, provider="yandex_direct")
        rows = list(csv.DictReader(StringIO(response.text), delimiter="\t"))
        impressions = sum(int(_number(row.get("Impressions"))) for row in rows)
        clicks = sum(int(_number(row.get("Clicks"))) for row in rows)
        spend = round(sum(_number(row.get("Cost")) for row in rows), 2)
        conversions = round(sum(_number(row.get("Conversions")) for row in rows), 2)
        return AdvertisingSnapshot(
            "yandex_direct",
            period_start,
            period_end,
            impressions,
            clicks,
            spend,
            conversions,
            currency,
        )

    async def fetch(
        self, oauth_token: str, public_config: Mapping[str, Any], period_start: date, period_end: date
    ) -> AdvertisingSnapshot:
        return await self.fetch_advertising_snapshot(
            oauth_token=oauth_token,
            client_login=str(public_config.get("client_login") or "") or None,
            period_start=period_start,
            period_end=period_end,
            currency=str(public_config.get("currency") or "") or None,
        )


class YandexWebmasterProvider:
    BASE_URL = "https://api.webmaster.yandex.net/v4"

    def __init__(self, *, client_factory: _ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _factory

    @staticmethod
    def _host_name(url: str) -> str:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").lower().rstrip(".")

    async def verify(self, oauth_token: str, primary_hostname: str) -> dict[str, str]:
        expected = self._host_name(primary_hostname)
        if not expected:
            raise AnalyticsProviderError("yandex_webmaster_host_invalid", "Primary hostname is invalid")
        async with self._client_factory() as client:
            user = await client.get(f"{self.BASE_URL}/user", headers=_oauth(oauth_token))
            if user.status_code != 200:
                raise _provider_error(user, provider="yandex_webmaster")
            try:
                user_id = user.json()["user_id"]
            except (KeyError, TypeError, ValueError) as exc:
                raise AnalyticsProviderError("yandex_webmaster_invalid_response", "Provider returned an invalid response") from exc
            hosts = await client.get(f"{self.BASE_URL}/user/{user_id}/hosts", headers=_oauth(oauth_token))
        if hosts.status_code != 200:
            raise _provider_error(hosts, provider="yandex_webmaster")
        try:
            candidates = hosts.json().get("hosts", [])
        except ValueError as exc:
            raise AnalyticsProviderError("yandex_webmaster_invalid_response", "Provider returned an invalid response") from exc
        for host in candidates:
            if not isinstance(host, Mapping) or not host.get("verified"):
                continue
            if self._host_name(str(host.get("ascii_host_url") or "")) == expected:
                host_id = host.get("host_id")
                if isinstance(host_id, str) and host_id:
                    return {
                        "user_id": str(user_id),
                        "host_id": host_id,
                        "site_url": str(host.get("ascii_host_url") or ""),
                    }
        raise AnalyticsProviderError("yandex_webmaster_host_not_verified", "The exact primary hostname is not verified in Yandex Webmaster")

    async def fetch_popular_queries(
        self,
        *,
        oauth_token: str,
        user_id: int | str,
        host_id: str,
        limit: int = 100,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> tuple[SearchQueryRow, ...]:
        safe_limit = min(max(limit, 1), 500)
        async with self._client_factory() as client:
            response = await client.get(
                f"{self.BASE_URL}/user/{user_id}/hosts/{host_id}/search-queries/popular",
                headers=_oauth(oauth_token),
                params=[
                    ("order_by", "TOTAL_CLICKS"),
                    ("query_indicator", "TOTAL_SHOWS"),
                    ("query_indicator", "TOTAL_CLICKS"),
                    ("query_indicator", "AVG_SHOW_POSITION"),
                    ("device_type_indicator", "ALL"),
                    ("limit", str(safe_limit)),
                    *([("date_from", period_start.isoformat())] if period_start else []),
                    *([("date_to", period_end.isoformat())] if period_end else []),
                ],
            )
        if response.status_code != 200:
            raise _provider_error(response, provider="yandex_webmaster")
        try:
            queries = response.json().get("queries", [])
        except ValueError as exc:
            raise AnalyticsProviderError("yandex_webmaster_invalid_response", "Provider returned an invalid response") from exc
        rows: list[SearchQueryRow] = []
        for row in queries:
            if not isinstance(row, Mapping) or not row.get("query_text"):
                continue
            indicators = row.get("indicators")
            values = indicators if isinstance(indicators, Mapping) else row
            clicks = int(_number(values.get("TOTAL_CLICKS")))
            impressions = int(_number(values.get("TOTAL_SHOWS")))
            rows.append(
                SearchQueryRow(
                    query=str(row.get("query_text")),
                    clicks=clicks,
                    impressions=impressions,
                    ctr=round(clicks / impressions * 100, 2) if impressions else 0.0,
                    position=(
                        _number(values.get("AVG_SHOW_POSITION"))
                        if values.get("AVG_SHOW_POSITION") is not None
                        else None
                    ),
                )
            )
        return tuple(rows)

    async def fetch(
        self,
        oauth_token: str,
        public_config: Mapping[str, Any],
        *,
        limit: int = 100,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> SearchDemandProviderSnapshot:
        try:
            user_id, host_id = public_config["user_id"], public_config["host_id"]
        except KeyError as exc:
            raise AnalyticsProviderError("yandex_webmaster_config_invalid", "Webmaster connection needs to be connected again") from exc
        rows = await self.fetch_popular_queries(
            oauth_token=oauth_token,
            user_id=str(user_id),
            host_id=str(host_id),
            limit=limit,
            period_start=period_start,
            period_end=period_end,
        )
        return SearchDemandProviderSnapshot("yandex_webmaster", rows)
