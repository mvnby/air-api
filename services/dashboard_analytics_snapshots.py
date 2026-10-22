"""Read-only projection of durable source snapshots. Never starts refresh/HTTP."""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
import hashlib
import json

from core.config import settings
from crud import dashboard_analytics as store
from services.dashboard_marketing import MarketingProviderSnapshot, MarketingSnapshot, MarketingSourceSnapshot, resolve_metrika_counter_id
from services.dashboard_search_demand import SearchDemandSnapshot, SearchDemandProviderState, SearchDemandQuery

MARKETING_PROVIDERS = ("yandex_metrika", "yandex_direct", "google_analytics", "google_ads")
SEARCH_PROVIDERS = ("yandex_webmaster", "google_search_console")
SCHEMA_VERSION = 1


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def ttl(provider):
    return 10800 if provider in SEARCH_PROVIDERS else 3600


@dataclass(frozen=True)
class SourceConfiguration:
    provider: str
    revision: str


def revision(row):
    identity = [row.id, row.snapshot_revision, row.public_config]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def configurations(session, scope):
    rows = await store.connection_rows(session, scope)
    result = [SourceConfiguration(row.provider, revision(row)) for row in rows
              if row.status == "active" and row.provider in MARKETING_PROVIDERS + SEARCH_PROVIDERS]
    # Environment credentials are legacy system-owned and still require an exact storefront map.
    if scope.is_system and not any(row.provider == "yandex_metrika" for row in rows):
        counter = resolve_metrika_counter_id(scope, scoped_counters_json=settings.DASHBOARD_METRIKA_STOREFRONT_COUNTERS_JSON)
        if counter and settings.DASHBOARD_METRIKA_OAUTH_TOKEN:
            fingerprint = hashlib.sha256((counter + ":" + settings.DASHBOARD_METRIKA_OAUTH_TOKEN).encode()).hexdigest()
            result.append(SourceConfiguration("yandex_metrika", "env-" + fingerprint[:60]))
    return result


def key_values(scope, config, start, end):
    key = hashlib.sha256(f"{scope.tenant_id}:{scope.storefront_id}:{config.provider}:{config.revision}:{start}:{end}:{SCHEMA_VERSION}".encode()).hexdigest()
    return dict(key=key, tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                provider=config.provider, configuration_revision=config.revision,
                period_start=start, period_end=end, schema_version=SCHEMA_VERSION,
                failure_count=0)


def source_state(provider, rows, start, end, now):
    latest = max(rows, key=lambda row: row.period_end, default=None)
    success = max((row for row in rows if row.payload is not None and row.last_success_at), key=lambda row: row.period_end, default=None)
    state = dict(provider=provider, status="pending", period_start=start, period_end=end)
    if latest:
        state.update(last_attempt_at=latest.last_attempt_at, next_retry_at=latest.next_retry_at, error_code=latest.error_code)
    if success:
        stale = (bool(latest and latest.error_code) or success.period_end != end
                 or (utc(now) - utc(success.last_success_at)).total_seconds() >= ttl(provider))
        state.update(status="stale" if stale else "fresh", updated_at=success.last_success_at,
                     period_start=success.period_start, period_end=success.period_end)
        if stale:
            state["message"] = "Не удалось обновить; сохранены последние данные." if latest and latest.error_code else "Показан сохранённый снимок; обновление выполняется в фоне."
    elif latest and latest.error_code:
        state.update(status="error", message="Источник временно недоступен. Повторим обновление автоматически.")
    else:
        state["message"] = "Первый снимок готовится в фоне."
    return state, success.payload if success else None


def aggregate_status(states):
    statuses = {row.status for row in states} - {"unconfigured"}
    if not statuses:
        return "unconfigured"
    if statuses == {"fresh"}:
        return "fresh"
    if statuses & {"fresh", "stale"}:
        return "stale"
    return "error" if "error" in statuses else "pending"


async def read_sources(session, scope, providers, start, end, now):
    configs = [c for c in await configurations(session, scope) if c.provider in providers]
    records = await store.read_candidates(session, tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                                           configurations=configs, periods=[(start, end)])
    configured = {c.provider: c for c in configs}
    result = []
    for provider in providers:
        if provider not in configured:
            result.append((dict(provider=provider, status="unconfigured"), None))
        else:
            relevant = [r for r in records if r.provider == provider and r.configuration_revision == configured[provider].revision]
            result.append(source_state(provider, relevant, start, end, now))
    return result


def dataclass_row(cls, payload):
    allowed = {field.name for field in fields(cls)}
    return cls(**{k: v for k, v in payload.items() if k in allowed})


class SavedMarketingProvider:
    async def get_snapshot(self, *, session, tenant_scope, start, end_exclusive):
        sources = await read_sources(session, tenant_scope, MARKETING_PROVIDERS, start, end_exclusive, datetime.now(timezone.utc))
        providers = []
        reports = {}
        for state, payload in sources:
            report = (payload or {}).get("marketing", {})
            metric = next((item for item in report.get("providers", []) if item["provider"] == state["provider"]), {})
            providers.append(dataclass_row(MarketingProviderSnapshot, {**metric, **state}))
            if payload:
                reports[state["provider"]] = report
        traffic = reports.get("yandex_metrika") or reports.get("google_analytics") or {}
        ads = [reports[p] for p in ("yandex_direct", "google_ads") if p in reports]
        currencies = {a.get("currency") for a in ads}
        currency = next(iter(currencies)) if len(currencies) == 1 and None not in currencies else None
        spend = round(sum(a["ad_spend"] for a in ads), 2) if ads and currency and all(a.get("ad_spend") is not None for a in ads) else None
        def total(field):
            return sum(a[field] for a in ads) if ads and all(a.get(field) is not None for a in ads) else None
        clicks, impressions = total("clicks"), total("impressions")
        return MarketingSnapshot(status=aggregate_status(providers), visits=traffic.get("visits"),
            sources=tuple(MarketingSourceSnapshot(**s) for s in traffic.get("sources", [])),
            ad_spend=spend, clicks=clicks, impressions=impressions,
            ctr=round(clicks * 100 / impressions, 2) if clicks is not None and impressions else None,
            platform_conversions=total("platform_conversions"), currency=currency,
            bounce_rate=traffic.get("bounce_rate"), average_session_duration_seconds=traffic.get("average_session_duration_seconds"),
            providers=tuple(providers), updated_at=min((p.updated_at for p in providers if p.updated_at), default=None),
            message="Статистика обновляется в фоне; период и время показаны у каждого источника.")


class SavedSearchDemandProvider:
    async def get_snapshot(self, *, session, tenant_scope, start, end_exclusive):
        sources = await read_sources(session, tenant_scope, SEARCH_PROVIDERS, start, end_exclusive, datetime.now(timezone.utc))
        providers, queries = [], []
        for state, payload in sources:
            providers.append(dataclass_row(SearchDemandProviderState, state))
            for row in (payload or {}).get("search", {}).get("queries", []):
                queries.append(SearchDemandQuery(**row))
        queries.sort(key=lambda q: (q.clicks, q.impressions), reverse=True)
        return SearchDemandSnapshot(status=aggregate_status(providers), providers=tuple(providers), queries=tuple(queries[:1000]),
            updated_at=min((p.updated_at for p in providers if p.updated_at), default=None),
            message="Поисковые системы публикуют данные с задержкой. Снимки обновляются в фоне каждые три часа.")
