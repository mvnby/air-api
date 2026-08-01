import pytest

from services.catalog_purge_service import (
    CloudflareCatalogPurgeService,
    CloudflarePurgeConfig,
    CloudflarePurgeConfigurationError,
    build_catalog_purge_urls,
    build_catalog_purge_urls_for_targets,
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


def test_target_url_builder_is_canonical_across_input_order():
    first = build_catalog_purge_urls_for_targets(
        ["https://shop.mvn.by", "https://mvn.by"],
        ["/product/z/", "/catalog/", "/product/a/"],
    )
    second = build_catalog_purge_urls_for_targets(
        ["https://mvn.by", "https://shop.mvn.by"],
        ["/product/a/", "/product/z/", "/catalog/"],
    )

    assert first == second
    assert first == (
        "https://mvn.by/catalog/",
        "https://mvn.by/product/a/",
        "https://mvn.by/product/z/",
        "https://shop.mvn.by/catalog/",
        "https://shop.mvn.by/product/a/",
        "https://shop.mvn.by/product/z/",
    )


def test_cloudflare_config_rejects_origin_outside_its_single_zone():
    config = CloudflarePurgeConfig(
        zone_id="zone-123",
        api_token="secret-token",
        enabled=True,
        dry_run=False,
        public_site_url="https://mvn.by",
        zone_hostnames=("mvn.by",),
    )

    config.ensure_origins_belong_to_zone(
        ["https://mvn.by", "https://shop.mvn.by"]
    )
    with pytest.raises(
        CloudflarePurgeConfigurationError,
        match="outside the configured Cloudflare zone",
    ):
        config.ensure_origins_belong_to_zone(["https://seller.example"])


@pytest.mark.asyncio
async def test_live_purge_does_not_truncate_more_than_120_urls():
    posted_batches: list[list[str]] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            posted_batches.append(list(json["files"]))
            return FakeResponse()

    urls = tuple(f"https://mvn.by/product/product-{index}/" for index in range(125))
    config = CloudflarePurgeConfig(
        zone_id="zone-123",
        api_token="secret-token",
        enabled=True,
        dry_run=False,
        batch_size=30,
        min_interval_seconds=0,
    )

    result = await CloudflareCatalogPurgeService().purge_urls(
        scope="global:test",
        revision=9,
        urls=urls,
        config=config,
        http_client_factory=FakeClient,
    )

    assert result.url_count == 125
    assert result.attempted_batches == 5
    assert result.failed_batches == 0
    assert [url for batch in posted_batches for url in batch] == list(urls)


@pytest.mark.asyncio
async def test_live_purge_reports_partial_failure_and_continues_later_batches():
    posted_batches: list[list[str]] = []

    class FakeResponse:
        def __init__(self, *, success: bool):
            self.status_code = 200 if success else 429
            self._success = success

        def json(self):
            if self._success:
                return {"success": True}
            return {
                "success": False,
                "errors": [{"code": 1015, "message": "sensitive detail"}],
            }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            posted_batches.append(list(json["files"]))
            return FakeResponse(success=len(posted_batches) != 2)

    urls = tuple(f"https://mvn.by/product/product-{index}/" for index in range(65))
    config = CloudflarePurgeConfig(
        zone_id="zone-123",
        api_token="secret-token",
        enabled=True,
        dry_run=False,
        batch_size=30,
        min_interval_seconds=0,
    )

    result = await CloudflareCatalogPurgeService().purge_urls(
        scope="global:test",
        revision=10,
        urls=urls,
        config=config,
        http_client_factory=FakeClient,
    )

    assert result.attempted_batches == 3
    assert result.failed_batches == 1
    assert len(posted_batches) == 3
    assert result.errors == ("Cloudflare purge error codes: 1015",)
    assert "sensitive detail" not in " ".join(result.errors)
