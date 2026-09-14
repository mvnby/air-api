from __future__ import annotations

import hashlib
from dataclasses import replace

import httpx
import pytest

from services.brand_logo_cdn_backfill_service import (
    RULES,
    BrandLogoBackfillBlockedError,
    BrandLogoCdnBackfillService,
    BrandLogoDownloader,
    BrandLogoRule,
)
from services.catalog_media_policy import CatalogMediaKind, CatalogMediaPolicy


def test_reviewed_rules_cover_the_six_known_legacy_brand_logos() -> None:
    assert [(rule.brand_id, rule.slug, rule.extension) for rule in RULES] == [
        (2, "chigo", "svg"),
        (13, "ultima", "svg"),
        (50, "gree", "svg"),
        (14, "mitsubishi-heavy", "svg"),
        (51, "daikin", "svg"),
        (12, "energolux", "webp"),
    ]
    assert all(rule.old_url.startswith("https://") for rule in RULES)
    assert all(len(rule.source_content_hash) == 64 for rule in RULES)
    assert all(len(rule.target_content_hash) == 64 for rule in RULES)


@pytest.mark.asyncio
async def test_downloader_accepts_reviewed_svg_and_rejects_other_hosts(
    monkeypatch,
) -> None:
    content = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"></svg>'
    rule = BrandLogoRule(
        brand_id=1,
        title="Brand",
        slug="brand",
        old_url="https://logos.example/logo.svg",
        allowed_hosts=("logos.example",),
        source_content_hash=hashlib.sha256(content).hexdigest(),
        target_content_hash="0" * 64,
        extension="svg",
        width=20,
        height=10,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/svg+xml"},
            content=content,
            request=request,
        )

    monkeypatch.setattr(
        BrandLogoDownloader,
        "_resolve_addresses",
        staticmethod(lambda _host: {"8.8.8.8"}),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = BrandLogoDownloader(client=client)
    result = await downloader.download(rule)
    assert result.content_hash == rule.source_content_hash

    outside = replace(rule, old_url="https://other.example/logo.svg")
    with pytest.raises(BrandLogoBackfillBlockedError, match="boundary"):
        await downloader.download(outside)
    await client.aclose()


@pytest.mark.asyncio
async def test_svg_processing_uses_media_library_sanitizer() -> None:
    unsafe = b"""<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">
    <script>alert(1)</script><rect width="20" height="10" />
    </svg>"""
    with pytest.raises(ValueError, match="unsupported embedded content"):
        await BrandLogoCdnBackfillService._process(unsafe)


def test_brand_logo_targets_remain_inside_content_cdn_policy() -> None:
    for rule in RULES:
        target = f"https://cdn.mvn.by/library/original/{rule.target_content_hash}.{rule.extension}"
        assert CatalogMediaPolicy.is_allowed_cdn(target, kind=CatalogMediaKind.CONTENT)
