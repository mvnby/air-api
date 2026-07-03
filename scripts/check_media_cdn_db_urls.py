#!/usr/bin/env python3
"""Check stored DB media references against the public CDN.

The script is intended to run inside the API app container. It only reads DB
rows and fetches public CDN URLs; it does not print raw order metadata or any
storage credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
for path in (SCRIPT_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from check_media_cdn_public import (  # noqa: E402
    CdnFetchResult,
    default_urlopen,
    fetch_cdn_url,
    validate_fetch_result,
)


OBJECT_STORAGE_PROVIDERS = {"r2", "s3", "s3_compatible"}
UrlOpener = Callable[[Request, float], Any]


@dataclass(frozen=True)
class DbMediaRef:
    source: str
    object_id: str
    field: str
    storage_provider: str
    url: str | None


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _clean_url(value: Any) -> str | None:
    cleaned = _clean_string(value)
    return cleaned or None


def _is_object_storage_provider(value: Any) -> bool:
    return _clean_string(value).lower() in OBJECT_STORAGE_PROVIDERS


def iter_object_storage_entries(value: Any, *, path: str = "$") -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        if _is_object_storage_provider(value.get("storage_provider")):
            yield path, value
        for key, nested in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_object_storage_entries(nested, path=child_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from iter_object_storage_entries(nested, path=f"{path}[{index}]")


def refs_from_order_meta(order_id: int | str, technical_meta: Any) -> list[DbMediaRef]:
    refs: list[DbMediaRef] = []
    for path, entry in iter_object_storage_entries(technical_meta):
        refs.append(
            DbMediaRef(
                source="order_technical_meta",
                object_id=str(order_id),
                field=path,
                storage_provider=_clean_string(entry.get("storage_provider")).lower(),
                url=_clean_url(entry.get("url")),
            )
        )
    return refs


def validate_db_media_refs(
    refs: list[DbMediaRef],
    *,
    expected_cdn_base: str,
    min_db_cdn_urls: int,
    min_db_cdn_urls_by_source: Mapping[str, int] | None = None,
) -> list[str]:
    failures: list[str] = []
    normalized_base = expected_cdn_base.rstrip("/")
    cdn_count = 0
    cdn_count_by_source: dict[str, int] = {}

    for ref in refs:
        label = f"source={ref.source} object_id={ref.object_id} field={ref.field}"
        if not _is_object_storage_provider(ref.storage_provider):
            failures.append(f"{label} provider is not object storage: {ref.storage_provider or '-'}")
            continue
        if not ref.url:
            failures.append(f"{label} provider={ref.storage_provider} is missing public URL")
            continue

        parsed = urlparse(ref.url)
        if parsed.scheme not in {"http", "https"}:
            failures.append(f"{label} url is not absolute: {ref.url}")
            continue
        if not ref.url.startswith(f"{normalized_base}/"):
            failures.append(f"{label} url does not use {normalized_base}: {ref.url}")
            continue
        cdn_count += 1
        cdn_count_by_source[ref.source] = cdn_count_by_source.get(ref.source, 0) + 1

    if cdn_count < min_db_cdn_urls:
        failures.append(f"only {cdn_count} DB CDN media urls found; expected at least {min_db_cdn_urls}")

    for source, minimum in (min_db_cdn_urls_by_source or {}).items():
        actual = cdn_count_by_source.get(source, 0)
        if actual < minimum:
            failures.append(f"source {source} has {actual} DB CDN media urls; expected at least {minimum}")

    return failures


def parse_min_db_cdn_urls_by_source(value: str | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw_item in (value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"source threshold must look like source=count: {item}")
        source, raw_minimum = (part.strip() for part in item.split("=", 1))
        if not source:
            raise ValueError(f"source threshold is missing source name: {item}")
        try:
            minimum = int(raw_minimum)
        except ValueError as exc:
            raise ValueError(f"source threshold count must be an integer: {item}") from exc
        if minimum < 0:
            raise ValueError(f"source threshold count must be >= 0: {item}")
        result[source] = minimum
    return result


def summarize_refs_by_source(refs: list[DbMediaRef], *, expected_cdn_base: str) -> dict[str, dict[str, int]]:
    normalized_base = expected_cdn_base.rstrip("/")
    summary: dict[str, dict[str, int]] = {}
    for ref in refs:
        source_summary = summary.setdefault(ref.source, {"refs": 0, "cdn_urls": 0})
        source_summary["refs"] += 1
        if ref.url and ref.url.startswith(f"{normalized_base}/"):
            source_summary["cdn_urls"] += 1
    return summary


def unique_db_cdn_urls(refs: list[DbMediaRef], *, expected_cdn_base: str) -> list[str]:
    normalized_base = expected_cdn_base.rstrip("/")
    seen: set[str] = set()
    urls: list[str] = []
    for ref in refs:
        if not ref.url or not ref.url.startswith(f"{normalized_base}/"):
            continue
        if ref.url in seen:
            continue
        seen.add(ref.url)
        urls.append(ref.url)
    return urls


async def collect_db_media_refs(*, max_rows_per_source: int, order_scan_limit: int) -> list[DbMediaRef]:
    from sqlalchemy import String, cast, select

    from core.database import async_session_maker
    from models import MediaAsset, Order, ProductImageVariant

    refs: list[DbMediaRef] = []
    async with async_session_maker() as session:
        variant_rows = await session.execute(
            select(
                ProductImageVariant.id,
                ProductImageVariant.variant_type,
                ProductImageVariant.url,
                ProductImageVariant.storage_provider,
            )
            .where(ProductImageVariant.storage_provider.in_(sorted(OBJECT_STORAGE_PROVIDERS)))
            .order_by(ProductImageVariant.updated_at.desc(), ProductImageVariant.id.desc())
            .limit(max_rows_per_source)
        )
        for variant_id, variant_type, url, storage_provider in variant_rows.all():
            refs.append(
                DbMediaRef(
                    source="product_image_variant",
                    object_id=str(variant_id),
                    field=str(variant_type or "url"),
                    storage_provider=_clean_string(storage_provider).lower(),
                    url=_clean_url(url),
                )
            )

        media_rows = await session.execute(
            select(MediaAsset.id, MediaAsset.variant_type, MediaAsset.url, MediaAsset.storage_provider)
            .where(MediaAsset.storage_provider.in_(sorted(OBJECT_STORAGE_PROVIDERS)))
            .order_by(MediaAsset.updated_at.desc(), MediaAsset.id.desc())
            .limit(max_rows_per_source)
        )
        for asset_id, variant_type, url, storage_provider in media_rows.all():
            refs.append(
                DbMediaRef(
                    source="media_asset",
                    object_id=str(asset_id),
                    field=str(variant_type or "url"),
                    storage_provider=_clean_string(storage_provider).lower(),
                    url=_clean_url(url),
                )
            )

        order_rows = await session.execute(
            select(Order.id, Order.technical_meta)
            .where(cast(Order.technical_meta, String).ilike("%storage_provider%"))
            .order_by(Order.updated_at.desc(), Order.id.desc())
            .limit(order_scan_limit)
        )
        for order_id, technical_meta in order_rows.all():
            refs.extend(refs_from_order_meta(order_id, technical_meta))

    return refs


async def check_db_media_cdn(
    *,
    expected_cdn_base: str,
    min_db_cdn_urls: int,
    min_db_cdn_urls_by_source: Mapping[str, int] | None,
    max_rows_per_source: int,
    order_scan_limit: int,
    max_fetches: int,
    timeout: float,
    opener: UrlOpener = default_urlopen,
    skip_fetch: bool = False,
) -> tuple[list[DbMediaRef], list[CdnFetchResult], list[str]]:
    refs = await collect_db_media_refs(
        max_rows_per_source=max_rows_per_source,
        order_scan_limit=order_scan_limit,
    )
    failures = validate_db_media_refs(
        refs,
        expected_cdn_base=expected_cdn_base,
        min_db_cdn_urls=min_db_cdn_urls,
        min_db_cdn_urls_by_source=min_db_cdn_urls_by_source,
    )

    fetch_results: list[CdnFetchResult] = []
    if not skip_fetch:
        for url in unique_db_cdn_urls(refs, expected_cdn_base=expected_cdn_base)[:max_fetches]:
            try:
                result = fetch_cdn_url(url, timeout=timeout, opener=opener)
            except HTTPError as exc:
                failures.append(f"url={url} failed with HTTP {exc.code}")
                continue
            except URLError as exc:
                failures.append(f"url={url} failed: {exc.reason}")
                continue
            fetch_results.append(result)
            failures.extend(validate_fetch_result(result))

        if refs and not fetch_results:
            failures.append("no DB CDN media URLs were fetched")

    return refs, fetch_results, failures


def _print_ref(ref: DbMediaRef) -> None:
    print(
        "db_media_cdn_ref "
        f"source={ref.source} "
        f"object_id={ref.object_id} "
        f"field={ref.field} "
        f"provider={ref.storage_provider or '-'} "
        f"url={ref.url or '-'}"
    )


def _print_fetch(result: CdnFetchResult) -> None:
    print(
        "db_media_cdn_fetch "
        f"status={result.status} "
        f"content_type={result.content_type or '-'} "
        f"content_length={result.content_length or '-'} "
        f"cache_control={result.cache_control or '-'} "
        f"cf_cache_status={result.cf_cache_status or '-'} "
        f"url={result.url}"
    )


def _print_source_summary(source: str, counts: Mapping[str, int]) -> None:
    print(
        "db_media_cdn_source "
        f"source={source} "
        f"refs={counts.get('refs', 0)} "
        f"cdn_urls={counts.get('cdn_urls', 0)}"
    )


async def async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check DB-backed media CDN URLs.")
    parser.add_argument("--expected-cdn-base", default="https://cdn.mvn.by")
    parser.add_argument("--min-db-cdn-urls", type=int, default=3)
    parser.add_argument(
        "--min-db-cdn-urls-by-source",
        default="",
        help="Comma-separated per-source thresholds, for example product_image_variant=1,media_asset=1.",
    )
    parser.add_argument("--max-rows-per-source", type=int, default=20)
    parser.add_argument("--order-scan-limit", type=int, default=200)
    parser.add_argument("--max-fetches", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args(argv)

    try:
        min_db_cdn_urls_by_source = parse_min_db_cdn_urls_by_source(args.min_db_cdn_urls_by_source)
        refs, fetch_results, failures = await check_db_media_cdn(
            expected_cdn_base=args.expected_cdn_base,
            min_db_cdn_urls=args.min_db_cdn_urls,
            min_db_cdn_urls_by_source=min_db_cdn_urls_by_source,
            max_rows_per_source=max(1, args.max_rows_per_source),
            order_scan_limit=max(1, args.order_scan_limit),
            max_fetches=max(1, args.max_fetches),
            timeout=args.timeout,
            skip_fetch=args.skip_fetch,
        )
    except Exception as exc:
        print(f"db_media_cdn_status=error error_type={type(exc).__name__} error={exc}", file=sys.stderr)
        return 1

    for ref in refs:
        _print_ref(ref)
    for source, counts in sorted(summarize_refs_by_source(refs, expected_cdn_base=args.expected_cdn_base).items()):
        _print_source_summary(source, counts)
    for result in fetch_results:
        _print_fetch(result)

    if failures:
        for failure in failures:
            print(f"db_media_cdn_failure={failure}", file=sys.stderr)
        return 1

    print(
        "db_media_cdn_status=passed "
        f"db_media_refs={len(refs)} "
        f"cdn_urls_checked={len(fetch_results)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
