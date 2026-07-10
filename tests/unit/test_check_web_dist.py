import json
from pathlib import Path

import pytest

from scripts.check_web_dist import validate_dist


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    asset = dist / "_astro/app.123.js"
    asset.parent.mkdir(parents=True)
    asset.write_text("console.log('ok')", encoding="utf-8")
    for index in range(10):
        page = dist / ("index.html" if index == 0 else f"page-{index}/index.html")
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text('<html><script src="/_astro/app.123.js"></script></html>', encoding="utf-8")
    catalog = dist / "catalog/index.html"
    catalog.parent.mkdir(parents=True)
    catalog.write_text('<html><script src="/_astro/app.123.js"></script></html>', encoding="utf-8")
    return dist


def test_validate_dist_accepts_complete_static_build(tmp_path):
    html_count, asset_count = validate_dist(_dist(tmp_path))

    assert html_count == 11
    assert asset_count == 1


def test_validate_dist_requires_matching_release_marker(tmp_path):
    dist = _dist(tmp_path)
    sha = "a" * 40
    (dist / "release.json").write_text(json.dumps({"sha": sha}), encoding="utf-8")

    validate_dist(dist, sha)

    with pytest.raises(RuntimeError, match="does not match"):
        validate_dist(dist, "b" * 40)


def test_validate_dist_rejects_missing_referenced_asset(tmp_path):
    dist = _dist(tmp_path)
    (dist / "_astro/app.123.js").unlink()

    with pytest.raises(RuntimeError, match="referenced static assets are missing"):
        validate_dist(dist)


def test_validate_dist_rejects_localhost_leak(tmp_path):
    dist = _dist(tmp_path)
    (dist / "index.html").write_text("<html>http://localhost:8000</html>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="development URL leaked"):
        validate_dist(dist)


def test_validate_dist_rejects_same_origin_media_dependency(tmp_path):
    dist = _dist(tmp_path)
    (dist / "index.html").write_text(
        '<html><img src="/media/library/crop/hash.webp"></html>',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="incompatible with Pages"):
        validate_dist(dist)
