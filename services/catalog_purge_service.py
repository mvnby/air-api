"""Cloudflare purge helpers for public catalog freshness."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_SITE_URL = "https://mvn.by"
CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_PURGE_FILES_LIMIT = 30
CLOUDFLARE_PURGE_MIN_INTERVAL_SECONDS = 0.25
CLOUDFLARE_PURGE_TIMEOUT_SECONDS = 10.0


class AsyncHttpClient(Protocol):
    async def __aenter__(self) -> "AsyncHttpClient":
        ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> Any:
        ...


HttpClientFactory = Callable[..., AsyncHttpClient]


@dataclass(frozen=True)
class CloudflarePurgeConfig:
    zone_id: str = ""
    api_token: str = field(default="", repr=False)
    enabled: bool = False
    dry_run: bool = True
    public_site_url: str = DEFAULT_PUBLIC_SITE_URL
    # A single worker currently owns one Cloudflare zone. Hostnames outside
    # these suffixes must be routed to a future per-zone worker instead of
    # being sent to the wrong zone and retried indefinitely.
    zone_hostnames: tuple[str, ...] = ()
    batch_size: int = CLOUDFLARE_PURGE_FILES_LIMIT
    min_interval_seconds: float = CLOUDFLARE_PURGE_MIN_INTERVAL_SECONDS
    timeout_seconds: float = CLOUDFLARE_PURGE_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "CloudflarePurgeConfig":
        return cls(
            zone_id=os.getenv("CLOUDFLARE_ZONE_ID", "").strip(),
            api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            enabled=_env_bool("CLOUDFLARE_PURGE_ENABLED", default=False),
            dry_run=_env_bool("CLOUDFLARE_PURGE_DRY_RUN", default=True),
            public_site_url=(
                os.getenv("PUBLIC_SITE_URL", "").strip()
                or os.getenv("WEBSITE_URL", "").strip()
                or DEFAULT_PUBLIC_SITE_URL
            ),
            zone_hostnames=_env_csv("CLOUDFLARE_PURGE_ZONE_HOSTNAMES"),
            batch_size=_env_int("CLOUDFLARE_PURGE_BATCH_SIZE", CLOUDFLARE_PURGE_FILES_LIMIT),
            min_interval_seconds=_env_float(
                "CLOUDFLARE_PURGE_MIN_INTERVAL_SECONDS",
                CLOUDFLARE_PURGE_MIN_INTERVAL_SECONDS,
            ),
            timeout_seconds=_env_float(
                "CLOUDFLARE_PURGE_TIMEOUT_SECONDS",
                CLOUDFLARE_PURGE_TIMEOUT_SECONDS,
            ),
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.zone_id and self.api_token)

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.dry_run:
            return "dry_run"
        if not self.has_credentials:
            return "missing_config"
        return "live"

    @property
    def should_call_cloudflare(self) -> bool:
        return self.mode == "live"

    @property
    def activation_mode(self) -> str:
        if self.mode != "live":
            return self.mode
        try:
            zone_hostnames = self.effective_zone_hostnames
        except (CloudflarePurgeConfigurationError, ValueError):
            return "invalid_config"
        return "live" if zone_hostnames else "invalid_config"

    @property
    def effective_zone_hostnames(self) -> tuple[str, ...]:
        configured = tuple(
            sorted(
                {
                    hostname
                    for raw_value in self.zone_hostnames
                    if (hostname := _normalize_zone_hostname(raw_value))
                }
            )
        )
        if configured:
            return configured
        public_hostname = urlsplit(
            _normalize_public_site_url(self.public_site_url)
        ).hostname
        return (public_hostname.casefold(),) if public_hostname else ()

    def ensure_origins_belong_to_zone(self, origins: Iterable[str]) -> None:
        allowed = self.effective_zone_hostnames
        if not allowed:
            raise CloudflarePurgeConfigurationError(
                "Cloudflare purge zone hostname is not configured"
            )
        unsupported: list[str] = []
        for origin in origins:
            hostname = urlsplit(_normalize_public_site_url(origin)).hostname
            normalized = hostname.casefold() if hostname else ""
            if not normalized or not any(
                normalized == zone or normalized.endswith(f".{zone}")
                for zone in allowed
            ):
                unsupported.append(normalized or "invalid")
        if unsupported:
            raise CloudflarePurgeConfigurationError(
                "Catalog invalidation origin is outside the configured "
                "Cloudflare zone"
            )


@dataclass(frozen=True)
class CloudflarePurgeResult:
    mode: str
    url_count: int
    attempted_batches: int = 0
    failed_batches: int = 0
    errors: tuple[str, ...] = ()


class CloudflarePurgeConfigurationError(RuntimeError):
    """The configured Cloudflare zone cannot safely serve an event."""


def build_catalog_purge_urls(
    public_site_url: str,
    *,
    product_slugs: Optional[Iterable[str]] = None,
    brand_slugs: Optional[Iterable[str]] = None,
) -> tuple[str, ...]:
    base_url = _normalize_public_site_url(public_site_url)
    return tuple(
        f"{base_url}{path}"
        for path in build_catalog_purge_paths(
            product_slugs=product_slugs,
            brand_slugs=brand_slugs,
        )
    )


def build_catalog_purge_paths(
    *,
    product_slugs: Optional[Iterable[str]] = None,
    brand_slugs: Optional[Iterable[str]] = None,
) -> tuple[str, ...]:
    paths: list[str] = []

    for slug in _unique_slugs(product_slugs):
        paths.append(f"/product/{quote(slug, safe='')}/")
    for slug in _unique_slugs(brand_slugs):
        paths.append(f"/brands/{quote(slug, safe='')}/")

    paths.append("/brands/")
    paths.append("/catalog/")
    return tuple(_dedupe(paths))


def build_catalog_purge_urls_for_targets(
    origins: Iterable[str],
    paths: Iterable[str],
) -> tuple[str, ...]:
    normalized_origins = tuple(
        sorted(
            set(_normalize_public_site_url(origin) for origin in origins),
            key=str.casefold,
        )
    )
    normalized_paths = tuple(
        sorted(
            {
                str(path or "").strip()
                for path in paths
                if str(path or "").strip().startswith("/")
            }
        )
    )
    return tuple(
        f"{origin}{path}"
        for origin in normalized_origins
        for path in normalized_paths
    )


def normalize_catalog_origin(raw_url: str) -> str:
    return _normalize_public_site_url(raw_url)


class CloudflareCatalogPurgeService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def purge_after_revision(
        self,
        *,
        scope: str,
        revision: int,
        product_slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
        config: Optional[CloudflarePurgeConfig] = None,
        http_client_factory: Optional[HttpClientFactory] = None,
    ) -> CloudflarePurgeResult:
        purge_config = config or CloudflarePurgeConfig.from_env()
        urls = build_catalog_purge_urls(
            purge_config.public_site_url,
            product_slugs=product_slugs,
            brand_slugs=brand_slugs,
        )
        return await self.purge_urls(
            scope=scope,
            revision=revision,
            urls=urls,
            config=purge_config,
            http_client_factory=http_client_factory,
        )

    async def purge_urls(
        self,
        *,
        scope: str,
        revision: int,
        urls: Iterable[str],
        config: Optional[CloudflarePurgeConfig] = None,
        http_client_factory: Optional[HttpClientFactory] = None,
    ) -> CloudflarePurgeResult:
        purge_config = config or CloudflarePurgeConfig.from_env()
        normalized_urls = tuple(
            _dedupe(str(url).strip() for url in urls if str(url).strip())
        )

        if not purge_config.should_call_cloudflare:
            logger.info(
                "Cloudflare catalog purge skipped mode=%s scope=%s revision=%s url_count=%s",
                purge_config.mode,
                scope,
                revision,
                len(normalized_urls),
            )
            return CloudflarePurgeResult(
                mode=purge_config.mode,
                url_count=len(normalized_urls),
            )

        try:
            return await self._purge_live(
                urls=normalized_urls,
                scope=scope,
                revision=revision,
                config=purge_config,
                http_client_factory=http_client_factory,
            )
        except Exception as exc:
            logger.warning(
                "Cloudflare catalog purge failed scope=%s revision=%s "
                "url_count=%s error_type=%s",
                scope,
                revision,
                len(normalized_urls),
                type(exc).__name__,
            )
            return CloudflarePurgeResult(
                mode="live",
                url_count=len(normalized_urls),
                failed_batches=1,
                errors=(f"Cloudflare request failed: {type(exc).__name__}",),
            )

    async def _purge_live(
        self,
        *,
        urls: tuple[str, ...],
        scope: str,
        revision: int,
        config: CloudflarePurgeConfig,
        http_client_factory: Optional[HttpClientFactory],
    ) -> CloudflarePurgeResult:
        endpoint = f"{CLOUDFLARE_API_BASE_URL}/zones/{config.zone_id}/purge_cache"
        factory = http_client_factory or httpx.AsyncClient
        batch_size = max(1, min(int(config.batch_size), CLOUDFLARE_PURGE_FILES_LIMIT))
        batches = [
            urls[index : index + batch_size]
            for index in range(0, len(urls), batch_size)
        ]
        attempted_batches = 0
        failed_batches = 0
        errors: list[str] = []

        for batch in batches:
            attempted_batches += 1
            await self._wait_for_rate_limit(config.min_interval_seconds)
            async with factory(timeout=config.timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {config.api_token}",
                        "Content-Type": "application/json",
                    },
                    json={"files": list(batch)},
                )

            success, error_summary = _parse_cloudflare_response(response)
            if success:
                logger.info(
                    "Cloudflare catalog purge ok scope=%s revision=%s batch_urls=%s status_code=%s",
                    scope,
                    revision,
                    len(batch),
                    getattr(response, "status_code", None),
                )
            else:
                failed_batches += 1
                errors.append(error_summary)
                logger.warning(
                    "Cloudflare catalog purge batch failed scope=%s revision=%s batch_urls=%s status_code=%s error=%s",
                    scope,
                    revision,
                    len(batch),
                    getattr(response, "status_code", None),
                    error_summary,
                )

        return CloudflarePurgeResult(
            mode="live",
            url_count=len(urls),
            attempted_batches=attempted_batches,
            failed_batches=failed_batches,
            errors=tuple(errors),
        )

    async def _wait_for_rate_limit(self, min_interval_seconds: float) -> None:
        min_interval = max(0.0, float(min_interval_seconds or 0))
        if min_interval <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            delay = self._last_request_at + min_interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()

def _normalize_public_site_url(raw_url: str) -> str:
    value = (raw_url or DEFAULT_PUBLIC_SITE_URL).strip()
    if not value:
        value = DEFAULT_PUBLIC_SITE_URL
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlsplit(value)
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    netloc = parsed.netloc or parsed.path
    return urlunsplit((scheme, netloc, "", "", "")).rstrip("/")


def _unique_slugs(values: Optional[Iterable[str]]) -> tuple[str, ...]:
    slugs: list[str] = []
    for value in values or []:
        slug = str(value or "").strip().strip("/")
        if not slug or slug.lower() in {"none", "null"}:
            continue
        slugs.append(slug)
    return tuple(_dedupe(slugs))


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


def _normalize_zone_hostname(raw_value: str) -> str:
    value = str(raw_value or "").strip().casefold().strip(".")
    if not value:
        return ""
    parsed = urlsplit(f"//{value}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CloudflarePurgeConfigurationError(
            "Cloudflare purge zone hostname is invalid"
        ) from exc
    if (
        not parsed.hostname
        or parsed.hostname != value
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise CloudflarePurgeConfigurationError(
            "Cloudflare purge zone hostname is invalid"
        )
    return value


def _parse_cloudflare_response(response: Any) -> tuple[bool, str]:
    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    success = 200 <= status_code < 300 and bool(payload.get("success", True))
    if success:
        return True, ""

    errors = payload.get("errors") if isinstance(payload, dict) else None
    if isinstance(errors, list) and errors:
        codes = []
        for item in errors[:3]:
            if isinstance(item, dict):
                code = item.get("code")
                if code is not None:
                    codes.append(str(code))
        if codes:
            return False, "Cloudflare purge error codes: " + ",".join(codes)
        return False, "Cloudflare purge request was rejected"

    return False, f"Cloudflare purge HTTP {status_code}"


cloudflare_catalog_purge_service = CloudflareCatalogPurgeService()
