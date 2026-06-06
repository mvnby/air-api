#!/usr/bin/env python3
"""Parse Yandex duplicate title/description CSV exports into SEO cleanup artifacts."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.seo.legacy_url_rules import GONE_URLS, REDIRECT_URLS

DEFAULT_BASE_URL = "https://mvn.by"
DEFAULT_OUTPUT_DIR = Path("var/seo")


@dataclass
class UrlIssue:
    url: str
    last_crawled: str = ""
    source_issues: set[str] = field(default_factory=set)
    duplicate_values: set[str] = field(default_factory=set)


def normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlsplit(raw)
        raw = parsed.path or "/"
        if parsed.query:
            raw = f"{raw}?{parsed.query}"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw


def read_yandex_duplicate_export(path: Path, issue_type: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    current_duplicate_value = ""

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            url = normalize_url(raw.get("Url", ""))
            value = str(raw.get("Value") or "").strip()
            if not url:
                if value:
                    current_duplicate_value = value
                continue
            rows.append((url, str(raw.get("LastAccess") or "").strip(), issue_type, value or current_duplicate_value))

    return rows


def merge_issues(exports: list[tuple[str, str, str, str]]) -> list[UrlIssue]:
    merged: dict[str, UrlIssue] = {}
    for url, last_crawled, issue_type, duplicate_value in exports:
        item = merged.setdefault(url, UrlIssue(url=url))
        if last_crawled and last_crawled > item.last_crawled:
            item.last_crawled = last_crawled
        item.source_issues.add(issue_type)
        if duplicate_value:
            item.duplicate_values.add(duplicate_value)
    return [merged[url] for url in sorted(merged)]


def classify_url(item: UrlIssue) -> str:
    if item.url in GONE_URLS:
        return GONE_URLS[item.url].classification
    if item.url in REDIRECT_URLS:
        return "legacy_route_duplicate"

    parsed = urlsplit(item.url)
    path = parsed.path.rstrip("/") or "/"
    duplicate_blob = " ".join(sorted(item.duplicate_values)).lower()

    if path == "/success":
        return "service_thank_you_page"
    if path.startswith("/product/"):
        return "current_product_page"
    if path in {"/split/haier/haier-home", "/split/haier/lightera"}:
        return "current_category_or_series_page"
    if path.startswith("/m-"):
        return "brand_or_manufacturer_landing_page"
    if path == "/index.php" and "_route_=" in parsed.query:
        return "legacy_route_duplicate"
    if "товар не найден" in duplicate_blob or parsed.query.startswith("product_id="):
        return "old_missing_product_or_legacy_dead_url"
    return "review"


def action_for(item: UrlIssue, classification: str) -> tuple[str, str, str, str]:
    if item.url in REDIRECT_URLS:
        rule = REDIRECT_URLS[item.url]
        return ("301_redirect_to_canonical_url", rule.target, "301", rule.note)
    if item.url in GONE_URLS:
        rule = GONE_URLS[item.url]
        return ("return_410_gone", "", "410", rule.note or "Exact obsolete URL from Yandex cleanup list.")

    if classification == "current_product_page":
        return (
            "keep_indexable; generate_unique_meta_description_from_product_data; ensure_canonical_self_url",
            "",
            "200 indexable canonical",
            "Active /product/ page; do not remove from index.",
        )
    if classification == "current_category_or_series_page":
        return (
            "keep_indexable; ensure_unique_title_description; canonical_self_url",
            "",
            "200 indexable canonical",
            "Clean category/series page should stay canonical.",
        )
    if classification == "brand_or_manufacturer_landing_page":
        return (
            "review_brand_canonical; 301_to_verified_/brands/<slug>/; otherwise_410_or_404",
            "",
            "301 if verified, otherwise 410/404",
            "Do not redirect to an unverified brand slug.",
        )
    if classification == "legacy_route_duplicate":
        return (
            "manual_review_before_redirect",
            "",
            "review",
            "No verified target in repository rules; do not guess.",
        )
    if classification == "service_thank_you_page":
        return ("set_noindex_or_exclude_from_sitemap", "", "noindex; excluded from sitemap", "Utility page.")
    return ("manual_review", "", "review", "Needs human verification.")


def build_action_rows(items: list[UrlIssue], base_url: str = DEFAULT_BASE_URL) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    base = base_url.rstrip("/")
    for item in items:
        classification = classify_url(item)
        action, target_url, expected_state, notes = action_for(item, classification)
        priority = "P0" if classification in {"old_missing_product_or_legacy_dead_url", "legacy_route_duplicate"} else "P1"
        rows.append(
            {
                "url": item.url,
                "full_url": f"{base}{item.url}",
                "last_crawled": item.last_crawled,
                "source_issues": ";".join(sorted(item.source_issues)),
                "duplicate_values": " | ".join(sorted(item.duplicate_values)),
                "classification": classification,
                "recommended_action": action,
                "target_url": target_url,
                "expected_http_or_indexing_state": expected_state,
                "priority": priority,
                "notes": notes,
            }
        )
    return rows


def write_artifacts(rows: list[dict[str, str]], output_dir: Path, base_url: str = DEFAULT_BASE_URL) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = output_dir / "yandex_url_action_matrix.csv"
    dead_path = output_dir / "yandex_dead_urls.txt"
    redirects_path = output_dir / "yandex_redirects.csv"
    indexnow_path = output_dir / "yandex_indexnow_urls.txt"

    fieldnames = [
        "url",
        "full_url",
        "last_crawled",
        "source_issues",
        "duplicate_values",
        "classification",
        "recommended_action",
        "target_url",
        "expected_http_or_indexing_state",
        "priority",
        "notes",
    ]
    with matrix_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    dead_rows = [row for row in rows if row["expected_http_or_indexing_state"] == "410"]
    dead_path.write_text("\n".join(row["full_url"] for row in dead_rows) + ("\n" if dead_rows else ""), encoding="utf-8")

    redirect_rows = [row for row in rows if row["expected_http_or_indexing_state"] == "301"]
    with redirects_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_url", "target_url", "status"])
        writer.writeheader()
        for row in redirect_rows:
            writer.writerow({"source_url": row["full_url"], "target_url": row["target_url"], "status": "301"})

    changed = []
    for row in rows:
        if row["classification"] in {
            "current_product_page",
            "current_category_or_series_page",
            "brand_or_manufacturer_landing_page",
        }:
            changed.append(row["full_url"])
        elif row["expected_http_or_indexing_state"] in {"301", "410"}:
            changed.append(row["full_url"])
            if row["target_url"].startswith("/"):
                changed.append(f"{base_url.rstrip('/')}{row['target_url']}")

    indexnow_path.write_text("\n".join(dict.fromkeys(changed)) + ("\n" if changed else ""), encoding="utf-8")


def generate_report(title_csv: Path, description_csv: Path, output_dir: Path, base_url: str) -> list[dict[str, str]]:
    exports = []
    exports.extend(read_yandex_duplicate_export(title_csv, "duplicate_title"))
    exports.extend(read_yandex_duplicate_export(description_csv, "duplicate_description"))
    rows = build_action_rows(merge_issues(exports), base_url=base_url)
    write_artifacts(rows, output_dir, base_url=base_url)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title-csv", required=True, type=Path, help="Yandex duplicate title CSV export")
    parser.add_argument("--description-csv", required=True, type=Path, help="Yandex duplicate description CSV export")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    rows = generate_report(args.title_csv, args.description_csv, args.output_dir, args.base_url)
    print(f"Wrote SEO artifacts to {args.output_dir} ({len(rows)} URLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
