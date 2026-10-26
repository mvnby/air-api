import json

import httpx
import pytest

from services import indexnow_service as module
from services.indexnow_service import (
    INDEXNOW_ENDPOINT,
    INDEXNOW_KEY_LOCATION,
    IndexNowPayload,
    IndexNowProviderError,
    IndexNowRejected,
    IndexNowService,
    catalog_indexnow_urls,
)
from services.indexnow_worker import IndexNowWorker


def test_only_canonical_catalog_paths_are_sent_and_unicode_is_encoded():
    paths = [
        "/catalog/", "/product/old/", "/product/new/", "/product/new/",
        "/product/модель/", "/brands/tcl/series/elite/",
        "/checkout/", "/manager/", "/api/", "/product/a/?utm_source=test",
        "//evil.example/", "/product/../", "/product/%2e%2e/",
        "/product/x%2Fy/", "/product/a/#secret", "/product/a%3Fb/",
    ]
    urls = catalog_indexnow_urls(["https://mvn.by", "https://test1.mvn.by"], paths)
    assert urls == sorted([
        "https://mvn.by/catalog/", "https://mvn.by/product/old/",
        "https://mvn.by/product/new/", "https://mvn.by/product/%D0%BC%D0%BE%D0%B4%D0%B5%D0%BB%D1%8C/",
        "https://mvn.by/brands/tcl/series/elite/",
    ])
    assert catalog_indexnow_urls(["https://test1.mvn.by"], paths) == []


@pytest.mark.parametrize("url", [
    "https://evil.example/product/a/", "http://mvn.by/product/a/",
    "https://mvn.by/product/a/?token=private", "https://user:pass@mvn.by/product/a/",
    "https://mvn.by:443/product/a/", "https://mvn.by/checkout/",
])
def test_payload_rejects_noncanonical_or_private_urls(url):
    with pytest.raises(ValueError):
        IndexNowPayload(catalog_event_id="a" * 32, tenant_id=1, storefront_id=1, urls=[url])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 202, 403, 429, 500, 400, 422])
async def test_provider_checks_public_key_and_classifies_receipt(monkeypatch, status):
    calls = []
    urls = ["https://mvn.by/product/old/", "https://mvn.by/product/new/"]

    def handler(request):
        calls.append(request)
        assert request.headers["user-agent"] == "MVN-IndexNow/1.0 (+https://mvn.by/)"
        if request.method == "GET":
            assert str(request.url) == INDEXNOW_KEY_LOCATION
            return httpx.Response(200, text="a" * 32 + "\n")
        assert str(request.url) == INDEXNOW_ENDPOINT
        body = json.loads(request.content)
        assert body == {"host": "mvn.by", "key": "a" * 32, "keyLocation": INDEXNOW_KEY_LOCATION, "urlList": sorted(urls)}
        return httpx.Response(status)

    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if status in {200, 202}:
        receipt = await IndexNowService().submit(urls)
        assert receipt.status_code == status
        assert receipt.url_count == 2
    else:
        expected = IndexNowRejected if status in {400, 422} else IndexNowProviderError
        with pytest.raises(expected):
            await IndexNowService().submit(urls)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_missing_or_redirected_key_never_submits(monkeypatch):
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/key"})

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(IndexNowProviderError):
        await IndexNowService().submit(["https://mvn.by/product/a/"])
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_disabled_worker_performs_no_database_or_provider_io():
    def forbidden_session():
        raise AssertionError("Disabled IndexNow must not open a session")

    assert await IndexNowWorker(session_factory=forbidden_session, enabled=False).run_once() == "disabled"
