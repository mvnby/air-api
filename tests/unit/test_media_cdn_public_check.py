import importlib.util
import json
import sys
from email.message import Message
from pathlib import Path
from urllib.error import URLError


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/check_media_cdn_public.py"
SPEC = importlib.util.spec_from_file_location("check_media_cdn_public", MODULE_PATH)
check_media_cdn_public = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_media_cdn_public
SPEC.loader.exec_module(check_media_cdn_public)


class FakeResponse:
    def __init__(self, body: bytes, *, status=200, headers=None):
        self._body = body
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    def getcode(self):
        return self.status


def fake_opener_factory(responses):
    def opener(request, timeout):
        url = request.full_url
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    return opener


def product_payload(*urls):
    return {
        "items": [
            {
                "id": index,
                "slug": f"product-{index}",
                "main_image": url,
                "card_image": url,
                "full_image": url,
            }
            for index, url in enumerate(urls, start=1)
        ]
    }


def test_media_cdn_check_passes_for_cacheable_cdn_images():
    products_url = "https://api.example.test/products"
    cdn_url = "https://cdn.mvn.by/products/variants/original/hash.webp"
    responses = {
        products_url: FakeResponse(json.dumps(product_payload(cdn_url)).encode()),
        cdn_url: FakeResponse(
            b"RIFF",
            headers={
                "content-type": "image/webp",
                "content-length": "4",
                "cache-control": "public, max-age=31536000, immutable",
                "cf-cache-status": "HIT",
            },
        ),
    }

    image_urls, fetch_results, failures = check_media_cdn_public.check_media_cdn(
        products_url=products_url,
        expected_cdn_base="https://cdn.mvn.by",
        min_cdn_urls=3,
        max_fetches=5,
        timeout=1,
        opener=fake_opener_factory(responses),
    )

    assert failures == []
    assert len(image_urls) == 3
    assert len(fetch_results) == 1
    assert fetch_results[0].cf_cache_status == "HIT"


def test_media_cdn_check_fails_when_primary_image_is_not_cdn():
    products_url = "https://api.example.test/products"
    source_url = "https://supplier.example.test/image.jpg"
    responses = {
        products_url: FakeResponse(json.dumps(product_payload(source_url)).encode()),
    }

    _, _, failures = check_media_cdn_public.check_media_cdn(
        products_url=products_url,
        expected_cdn_base="https://cdn.mvn.by",
        min_cdn_urls=1,
        max_fetches=5,
        timeout=1,
        opener=fake_opener_factory(responses),
    )

    assert any("does not use https://cdn.mvn.by" in failure for failure in failures)
    assert any("no CDN media URLs were fetched" in failure for failure in failures)


def test_media_cdn_check_fails_when_cdn_object_is_not_cacheable():
    products_url = "https://api.example.test/products"
    cdn_url = "https://cdn.mvn.by/products/variants/original/hash.webp"
    responses = {
        products_url: FakeResponse(json.dumps(product_payload(cdn_url)).encode()),
        cdn_url: FakeResponse(
            b"RIFF",
            headers={
                "content-type": "image/webp",
                "cache-control": "private, no-store",
            },
        ),
    }

    _, fetch_results, failures = check_media_cdn_public.check_media_cdn(
        products_url=products_url,
        expected_cdn_base="https://cdn.mvn.by",
        min_cdn_urls=1,
        max_fetches=5,
        timeout=1,
        opener=fake_opener_factory(responses),
    )

    assert len(fetch_results) == 1
    assert any("missing cacheable cache-control" in failure for failure in failures)


def test_media_cdn_check_reports_fetch_errors():
    products_url = "https://api.example.test/products"
    cdn_url = "https://cdn.mvn.by/products/variants/original/hash.webp"
    responses = {
        products_url: FakeResponse(json.dumps(product_payload(cdn_url)).encode()),
        cdn_url: URLError("connection refused"),
    }

    _, _, failures = check_media_cdn_public.check_media_cdn(
        products_url=products_url,
        expected_cdn_base="https://cdn.mvn.by",
        min_cdn_urls=1,
        max_fetches=5,
        timeout=1,
        opener=fake_opener_factory(responses),
    )

    assert any("connection refused" in failure for failure in failures)
