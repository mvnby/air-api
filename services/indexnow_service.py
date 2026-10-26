"""IndexNow provider boundary for canonical MVN catalog URLs only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


INDEXNOW_EVENT_TYPE = "search.indexnow.requested.v1"
INDEXNOW_ORIGIN = "https://mvn.by"
INDEXNOW_KEY_LOCATION = f"{INDEXNOW_ORIGIN}/indexnow-key.txt"
INDEXNOW_ENDPOINT = "https://yandex.com/indexnow"
_SEGMENT = re.compile(r"^[\w][\w.~-]*$", re.UNICODE)
_KEY = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def catalog_indexnow_urls(origins: list[str], paths: list[str]) -> list[str]:
    """Accept canonical catalog paths, never arbitrary additional purge paths."""
    if INDEXNOW_ORIGIN not in origins:
        return []
    urls: set[str] = set()
    for path in paths:
        if not path.startswith("/") or not path.endswith("/"):
            continue
        if any(character in path for character in ("?", "#", "\\")):
            continue
        segments = [unquote(part) for part in path.strip("/").split("/")]
        if not all(_SEGMENT.fullmatch(part) for part in segments):
            continue
        is_catalog = segments in (["catalog"], ["brands"])
        is_product_or_brand = len(segments) == 2 and segments[0] in {"product", "brands"}
        is_series = len(segments) == 4 and segments[0] == "brands" and segments[2] == "series"
        if is_catalog or is_product_or_brand or is_series:
            urls.add(INDEXNOW_ORIGIN + "/" + "/".join(quote(part, safe=".~_-") for part in segments) + "/")
    return sorted(urls)


class IndexNowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_event_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    tenant_id: int = Field(gt=0)
    storefront_id: int = Field(gt=0)
    urls: list[str] = Field(min_length=1, max_length=10000)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        expected = catalog_indexnow_urls(
            [INDEXNOW_ORIGIN],
            [urlsplit(value).path for value in values],
        )
        if sorted(set(values)) != expected:
            raise ValueError("IndexNow URLs must be canonical MVN catalog URLs")
        return expected


class IndexNowProviderError(RuntimeError):
    pass


class IndexNowRejected(IndexNowProviderError):
    """A malformed URL request needs operator review, not unlimited retries."""


@dataclass(frozen=True)
class IndexNowReceipt:
    status_code: int
    url_count: int


class IndexNowService:
    async def submit(self, urls: list[str]) -> IndexNowReceipt:
        # The key is a public ownership file. No OAuth or provider secret is
        # stored in the API. Root keyLocation also supports future key rotation.
        expected = catalog_indexnow_urls([INDEXNOW_ORIGIN], [urlsplit(url).path for url in urls])
        if not urls or sorted(set(urls)) != expected or len(expected) > 10000:
            raise IndexNowRejected("Invalid canonical IndexNow URL set")
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            key_response = await client.get(INDEXNOW_KEY_LOCATION)
            if key_response.status_code != 200 or len(key_response.content) > 256:
                raise IndexNowProviderError("Public IndexNow key is unavailable")
            key = key_response.text.strip()
            if not _KEY.fullmatch(key):
                raise IndexNowProviderError("Public IndexNow key is invalid")
            response = await client.post(
                INDEXNOW_ENDPOINT,
                json={
                    "host": "mvn.by",
                    "key": key,
                    "keyLocation": INDEXNOW_KEY_LOCATION,
                    "urlList": expected,
                },
            )
            if response.status_code in {400, 422}:
                raise IndexNowRejected(f"IndexNow rejected request: HTTP {response.status_code}")
            if response.status_code not in {200, 202}:
                raise IndexNowProviderError(f"IndexNow temporarily unavailable: HTTP {response.status_code}")
            # 202 explicitly means key validation pending; neither code proves
            # crawling or inclusion in search results.
            return IndexNowReceipt(response.status_code, len(expected))
