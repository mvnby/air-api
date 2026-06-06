import pytest

from services.catalog_purge_service import (
    CloudflareCatalogPurgeService,
    CloudflarePurgeConfig,
    build_catalog_purge_urls,
)


def test_build_catalog_purge_urls_exact_paths_and_dedupes():
    urls = build_catalog_purge_urls(
        "https://mvn.by/some/path?ignored=true",
        product_slugs=["alpha", "/beta/", "alpha"],
        brand_slugs=["daikin", "daikin"],
    )

    assert urls == (
        "https://mvn.by/product/alpha/",
        "https://mvn.by/product/beta/",
        "https://mvn.by/brands/daikin/",
        "https://mvn.by/brands/",
        "https://mvn.by/catalog/",
    )


@pytest.mark.asyncio
async def test_purge_defaults_to_safe_noop_without_env(monkeypatch):
    for name in (
        "CLOUDFLARE_PURGE_ENABLED",
        "CLOUDFLARE_PURGE_DRY_RUN",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    def fail_factory(**kwargs):
        raise AssertionError("HTTP client must not be created in no-env mode")

    result = await CloudflareCatalogPurgeService().purge_after_revision(
        scope="product_update",
        revision=1,
        product_slugs=["alpha"],
        http_client_factory=fail_factory,
    )

    assert result.mode == "disabled"
    assert result.url_count == 3
    assert result.attempted_batches == 0


@pytest.mark.asyncio
async def test_live_purge_posts_files_to_cloudflare_with_mocked_http():
    requests = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "result": {"id": "purge-id"}}

    class FakeClient:
        def __init__(self, **kwargs):
            requests.append({"factory_kwargs": kwargs})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            requests.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    config = CloudflarePurgeConfig(
        zone_id="zone-123",
        api_token="secret-token",
        enabled=True,
        dry_run=False,
        public_site_url="https://mvn.by",
        min_interval_seconds=0,
    )

    result = await CloudflareCatalogPurgeService().purge_after_revision(
        scope="product_update",
        revision=5,
        product_slugs=["alpha"],
        brand_slugs=["daikin"],
        config=config,
        http_client_factory=FakeClient,
    )

    post_request = requests[1]
    assert result.mode == "live"
    assert result.attempted_batches == 1
    assert result.failed_batches == 0
    assert post_request["url"] == (
        "https://api.cloudflare.com/client/v4/zones/zone-123/purge_cache"
    )
    assert post_request["headers"]["Authorization"] == "Bearer secret-token"
    assert post_request["json"] == {
        "files": [
            "https://mvn.by/product/alpha/",
            "https://mvn.by/brands/daikin/",
            "https://mvn.by/brands/",
            "https://mvn.by/catalog/",
        ]
    }
