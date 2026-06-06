#!/usr/bin/env python3
"""Curl-based QA checks for the Yandex SEO cleanup rules and metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.seo.legacy_url_rules import GONE_RULES, LEGACY_REDIRECT_RULES

FALLBACK_DESCRIPTION = "Кондиционеры в Витебске. Продажа, монтаж, обслуживание"
PRODUCT_SAMPLES = (
    "/product/split-sistema-haier-tundra-hsu-12htt03r3-hsu-12htt103r3out-2024/",
    "/product/split-sistema-kanalnogo-tipa-energolux-duct-6-sad18d6-a-sau18u6-a-ws40/",
)
BRAND_SAMPLES = ("/brands/tcl/", "/brands/haier/")
SERIES_SAMPLES = ("/split/haier/haier-home/", "/split/haier/lightera/")


def run_curl(args: list[str]) -> str:
    result = subprocess.run(["curl", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"curl exited with {result.returncode}")
    return result.stdout


def status_and_redirect(url: str) -> tuple[int, str]:
    output = run_curl(["-sS", "-o", "/dev/null", "-w", "%{http_code}\t%{redirect_url}", "-I", url])
    code, _, redirect_url = output.partition("\t")
    return int(code), redirect_url.strip()


def fetch_html(url: str) -> str:
    return run_curl(["-fsSL", url])


def meta_descriptions(html: str) -> list[str]:
    matches = re.findall(
        r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html,
        flags=re.IGNORECASE,
    )
    return [unescape(value).strip() for value in matches]


def canonical_href(html: str) -> str:
    match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://mvn.by")
    parser.add_argument(
        "--canonical-base-url",
        default="https://mvn.by",
        help="Expected canonical origin; keep https://mvn.by when checking local Astro preview.",
    )
    parser.add_argument(
        "--skip-http-rules",
        action="store_true",
        help="Skip 301/410 checks when running against Astro preview without Apache/Nginx rules.",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    canonical_base = args.canonical_base_url.rstrip("/")
    failures: list[str] = []

    if not args.skip_http_rules:
        for rule in GONE_RULES:
            url = f"{base}{rule.source}"
            code, _ = status_and_redirect(url)
            if code not in {404, 410}:
                failures.append(f"Expected 404/410 for {url}, got {code}")

        for rule in LEGACY_REDIRECT_RULES:
            url = f"{base}{rule.source}"
            code, redirect_url = status_and_redirect(url)
            expected = f"{base}{rule.target}"
            if code != 301 or redirect_url.rstrip("/") != expected.rstrip("/"):
                failures.append(f"Expected 301 {expected} for {url}, got {code} {redirect_url}")

    product_descriptions = []
    for path in PRODUCT_SAMPLES:
        url = f"{base}{path}"
        html = fetch_html(url)
        descriptions = meta_descriptions(html)
        if len(descriptions) != 1:
            failures.append(f"Expected exactly one meta description for {url}, got {len(descriptions)}")
            continue
        description = descriptions[0]
        product_descriptions.append(description)
        if description == FALLBACK_DESCRIPTION or len(description) > 170:
            failures.append(f"Bad product meta description for {url}: {description!r}")
        expected_canonical = f"{canonical_base}{path}"
        if canonical_href(html).rstrip("/") != expected_canonical.rstrip("/"):
            failures.append(f"Bad product canonical for {url}: {canonical_href(html)!r}")

    if len(set(product_descriptions)) != len(product_descriptions):
        failures.append("Product sample descriptions are duplicated")

    for path in (*BRAND_SAMPLES, *SERIES_SAMPLES):
        url = f"{base}{path}"
        html = fetch_html(url)
        if len(meta_descriptions(html)) != 1:
            failures.append(f"Expected one meta description for {url}")
        expected_canonical = f"{canonical_base}{path}"
        if canonical_href(html).rstrip("/") != expected_canonical.rstrip("/"):
            failures.append(f"Bad canonical for {url}: {canonical_href(html)!r}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("SEO QA passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
