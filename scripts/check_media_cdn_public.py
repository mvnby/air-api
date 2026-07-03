#!/usr/bin/env python3
"""Check public catalog media CDN URLs without requiring secrets."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PRIMARY_IMAGE_FIELDS = ("main_image", "card_image", "full_image")
MEDIA_CONTENT_TYPES = ("image/", "application/octet-stream")


@dataclass(frozen=True)
class ProductImageUrl:
    product_id: str
    product_slug: str
    field: str
    url: str


@dataclass(frozen=True)
class CdnFetchResult:
    url: str
    status: int
    content_type: str
    cache_control: str
    cf_cache_status: str
    content_length: str


UrlOpener = Callable[[Request, float], Any]


def default_urlopen(request: Request, timeout: float) -> Any:
    return urlopen(request, timeout=timeout)


def load_json_url(url: str, *, timeout: float, opener: UrlOpener = default_urlopen) -> Any:
    request = Request(url, headers={"User-Agent": "mvn-media-cdn-check/1.0"})
    with opener(request, timeout) as response:
        charset = response.headers.get_content_charset("utf-8")
        return json.loads(response.read().decode(charset))


def product_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        items = payload.get("items")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("products payload must be a list or an object with list field 'items'")
    return [item for item in items if isinstance(item, Mapping)]


def _product_label(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if value is None:
        return ""
    return str(value)


def collect_primary_image_urls(items: list[Mapping[str, Any]]) -> list[ProductImageUrl]:
    collected: list[ProductImageUrl] = []
    for index, item in enumerate(items, start=1):
        product_id = _product_label(item, "id") or str(index)
        product_slug = _product_label(item, "slug")
        for field in PRIMARY_IMAGE_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                collected.append(
                    ProductImageUrl(
                        product_id=product_id,
                        product_slug=product_slug,
                        field=field,
                        url=value.strip(),
                    )
                )
    return collected


def validate_primary_urls(
    urls: list[ProductImageUrl],
    *,
    expected_cdn_base: str,
    min_cdn_urls: int,
) -> list[str]:
    failures: list[str] = []
    normalized_base = expected_cdn_base.rstrip("/")
    cdn_count = 0

    for image_url in urls:
        parsed = urlparse(image_url.url)
        if parsed.scheme not in {"http", "https"}:
            failures.append(
                f"product={image_url.product_id} field={image_url.field} url is not absolute: "
                f"{image_url.url}"
            )
            continue
        if not image_url.url.startswith(f"{normalized_base}/"):
            failures.append(
                f"product={image_url.product_id} field={image_url.field} url does not use "
                f"{normalized_base}: {image_url.url}"
            )
            continue
        cdn_count += 1

    if cdn_count < min_cdn_urls:
        failures.append(f"only {cdn_count} CDN primary image urls found; expected at least {min_cdn_urls}")

    return failures


def unique_cdn_urls(urls: list[ProductImageUrl], *, expected_cdn_base: str) -> list[str]:
    normalized_base = expected_cdn_base.rstrip("/")
    seen: set[str] = set()
    unique: list[str] = []
    for image_url in urls:
        if not image_url.url.startswith(f"{normalized_base}/"):
            continue
        if image_url.url in seen:
            continue
        seen.add(image_url.url)
        unique.append(image_url.url)
    return unique


def fetch_cdn_url(url: str, *, timeout: float, opener: UrlOpener = default_urlopen) -> CdnFetchResult:
    request = Request(url, headers={"User-Agent": "mvn-media-cdn-check/1.0"})
    with opener(request, timeout) as response:
        response.read(1024)
        return CdnFetchResult(
            url=url,
            status=getattr(response, "status", response.getcode()),
            content_type=response.headers.get("content-type", ""),
            cache_control=response.headers.get("cache-control", ""),
            cf_cache_status=response.headers.get("cf-cache-status", ""),
            content_length=response.headers.get("content-length", ""),
        )


def validate_fetch_result(result: CdnFetchResult) -> list[str]:
    failures: list[str] = []
    if result.status != 200:
        failures.append(f"url={result.url} returned HTTP {result.status}")

    if result.content_type and not result.content_type.lower().startswith(MEDIA_CONTENT_TYPES):
        failures.append(f"url={result.url} returned unexpected content-type={result.content_type}")

    cache_control = result.cache_control.lower()
    if "public" not in cache_control or "max-age=" not in cache_control:
        failures.append(f"url={result.url} missing cacheable cache-control: {result.cache_control}")

    return failures


def check_media_cdn(
    *,
    products_url: str,
    expected_cdn_base: str,
    min_cdn_urls: int,
    max_fetches: int,
    timeout: float,
    opener: UrlOpener = default_urlopen,
) -> tuple[list[ProductImageUrl], list[CdnFetchResult], list[str]]:
    payload = load_json_url(products_url, timeout=timeout, opener=opener)
    items = product_items(payload)
    image_urls = collect_primary_image_urls(items)
    failures = validate_primary_urls(
        image_urls,
        expected_cdn_base=expected_cdn_base,
        min_cdn_urls=min_cdn_urls,
    )

    fetch_results: list[CdnFetchResult] = []
    for url in unique_cdn_urls(image_urls, expected_cdn_base=expected_cdn_base)[:max_fetches]:
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

    if not fetch_results:
        failures.append("no CDN media URLs were fetched")

    return image_urls, fetch_results, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check public media CDN URLs from catalog API.")
    parser.add_argument(
        "--products-url",
        default="https://api.mvn.by/api/v1/products?limit=5",
        help="Public products API URL to sample.",
    )
    parser.add_argument(
        "--expected-cdn-base",
        default="https://cdn.mvn.by",
        help="Required public CDN URL prefix.",
    )
    parser.add_argument(
        "--min-cdn-urls",
        type=int,
        default=3,
        help="Minimum number of primary product image URLs that must use the CDN.",
    )
    parser.add_argument(
        "--max-fetches",
        type=int,
        default=5,
        help="Maximum unique CDN media objects to fetch.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    args = parser.parse_args(argv)

    try:
        image_urls, fetch_results, failures = check_media_cdn(
            products_url=args.products_url,
            expected_cdn_base=args.expected_cdn_base,
            min_cdn_urls=args.min_cdn_urls,
            max_fetches=args.max_fetches,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"media_cdn_status=error error_type={type(exc).__name__} error={exc}", file=sys.stderr)
        return 1

    for image_url in image_urls:
        print(
            "media_cdn_primary_image "
            f"product_id={image_url.product_id} "
            f"product_slug={image_url.product_slug or '-'} "
            f"field={image_url.field} "
            f"url={image_url.url}"
        )

    for result in fetch_results:
        print(
            "media_cdn_fetch "
            f"status={result.status} "
            f"content_type={result.content_type or '-'} "
            f"content_length={result.content_length or '-'} "
            f"cache_control={result.cache_control or '-'} "
            f"cf_cache_status={result.cf_cache_status or '-'} "
            f"url={result.url}"
        )

    if failures:
        for failure in failures:
            print(f"media_cdn_failure={failure}", file=sys.stderr)
        return 1

    print(
        "media_cdn_status=passed "
        f"primary_image_urls={len(image_urls)} "
        f"cdn_urls_checked={len(fetch_results)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
