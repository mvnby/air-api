#!/usr/bin/env python3
"""Validate the built static storefront before any production promotion."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src", "poster"} and value:
                self.references.add(value)


def local_asset_paths(html: str) -> set[str]:
    parser = AssetParser()
    parser.feed(html)
    paths: set[str] = set()
    for reference in parser.references:
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            continue
        path = unquote(parsed.path).lstrip("/")
        if path and Path(path).suffix:
            paths.add(path)
    return paths


def validate_dist(dist: Path, expected_release: str | None = None) -> tuple[int, int]:
    required_pages = ("index.html", "catalog/index.html")
    for relative in required_pages:
        path = dist / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"required page is missing or empty: {relative}")

    if expected_release is not None:
        release_path = dist / "release.json"
        try:
            release = json.loads(release_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError("release.json is missing or invalid") from exc
        if release != {"sha": expected_release}:
            raise RuntimeError("release.json does not match the expected release SHA")

    html_files = sorted(dist.rglob("*.html"))
    if len(html_files) < 10:
        raise RuntimeError(f"static build has too few HTML pages: {len(html_files)}")

    missing_assets: set[str] = set()
    referenced_assets: set[str] = set()
    same_origin_media: set[str] = set()
    for html_path in html_files:
        html = html_path.read_text(encoding="utf-8")
        if "http://127.0.0.1" in html or "http://localhost" in html:
            raise RuntimeError(f"local development URL leaked into {html_path.relative_to(dist)}")
        for asset in local_asset_paths(html):
            referenced_assets.add(asset)
            if asset.startswith("media/"):
                same_origin_media.add(asset)
            if not (dist / asset).is_file():
                missing_assets.add(asset)

    if same_origin_media:
        sample = ", ".join(sorted(same_origin_media)[:10])
        raise RuntimeError(f"same-origin media paths are incompatible with Pages: {sample}")
    if missing_assets:
        sample = ", ".join(sorted(missing_assets)[:10])
        raise RuntimeError(f"referenced static assets are missing: {sample}")
    if not any(asset.startswith("_astro/") for asset in referenced_assets):
        raise RuntimeError("build does not reference any _astro assets")

    return len(html_files), len(referenced_assets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--expected-release")
    args = parser.parse_args()
    try:
        html_count, asset_count = validate_dist(args.dist.resolve(), args.expected_release)
    except RuntimeError as exc:
        print(f"web_dist_status=failed reason={exc}")
        return 1
    print(f"web_dist_status=passed html_pages={html_count} referenced_assets={asset_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
