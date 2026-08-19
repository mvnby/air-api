"""Strict manifest contract for reviewed product-media URL repairs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_URL_RE = re.compile(
    r"^https://cdn\.mvn\.by/products/(?:shared|variants/original)/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.(?:avif|gif|jpe?g|png|webp)$",
    re.IGNORECASE,
)


class ProductMediaUrlBackfillManifestError(ValueError):
    pass


def is_canonical_product_media_url(value: str) -> bool:
    candidate = str(value or "").strip()
    if (
        not candidate.startswith("https://cdn.mvn.by/")
        or not _CANONICAL_URL_RE.fullmatch(candidate)
        or ".." in candidate
    ):
        return False
    parsed = urlsplit(candidate)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "cdn.mvn.by"
        and not parsed.username
        and not parsed.password
        and parsed.port is None
        and not parsed.query
        and not parsed.fragment
    )


@dataclass(frozen=True, slots=True)
class ProductMediaUrlSourceRule:
    old_url: str
    action: str
    expected_product_ids: tuple[int, ...]
    target_url: str | None = None
    fetch_url: str | None = None
    allowed_redirect_hosts: tuple[str, ...] = ()
    rights_review_ref: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProductMediaUrlBackfillManifest:
    version: int
    name: str
    public_catalog_url: str
    expected_public_product_count: int
    expected_public_snapshot_sha256: str
    expected_db_snapshot_sha256: str
    sources: tuple[ProductMediaUrlSourceRule, ...]
    fingerprint: str

    @classmethod
    def normalize(cls, payload: Any) -> "ProductMediaUrlBackfillManifest":
        if not isinstance(payload, dict):
            raise ProductMediaUrlBackfillManifestError("Manifest must be a JSON object")
        expected_keys = {
            "version",
            "name",
            "public_catalog_url",
            "expected_public_product_count",
            "expected_public_snapshot_sha256",
            "expected_db_snapshot_sha256",
            "sources",
        }
        if set(payload) != expected_keys:
            raise ProductMediaUrlBackfillManifestError(
                "Manifest fields do not match the reviewed v1 contract"
            )
        if payload["version"] != 1 or isinstance(payload["version"], bool):
            raise ProductMediaUrlBackfillManifestError("Manifest version must be 1")
        name = str(payload["name"] or "").strip()
        if not name or len(name) > 100:
            raise ProductMediaUrlBackfillManifestError("Manifest name is invalid")
        public_catalog_url = cls._normalize_catalog_url(payload["public_catalog_url"])
        count = payload["expected_public_product_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100_000:
            raise ProductMediaUrlBackfillManifestError(
                "expected_public_product_count is invalid"
            )
        public_hash = cls._normalize_digest(
            payload["expected_public_snapshot_sha256"],
            "expected_public_snapshot_sha256",
        )
        db_hash = cls._normalize_digest(
            payload["expected_db_snapshot_sha256"],
            "expected_db_snapshot_sha256",
        )
        raw_sources = payload["sources"]
        if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= 100:
            raise ProductMediaUrlBackfillManifestError("sources must contain 1-100 rules")
        sources = tuple(cls._normalize_source(item) for item in raw_sources)
        old_urls = [item.old_url for item in sources]
        if len(old_urls) != len(set(old_urls)):
            raise ProductMediaUrlBackfillManifestError("Source old_url values must be unique")
        all_product_ids = [
            product_id
            for source in sources
            for product_id in source.expected_product_ids
        ]
        if len(all_product_ids) != len(set(all_product_ids)):
            raise ProductMediaUrlBackfillManifestError(
                "A product id may belong to only one source rule"
            )
        canonical = {
            "version": 1,
            "name": name,
            "public_catalog_url": public_catalog_url,
            "expected_public_product_count": count,
            "expected_public_snapshot_sha256": public_hash,
            "expected_db_snapshot_sha256": db_hash,
            "sources": [cls._source_payload(item) for item in sources],
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            version=1,
            name=name,
            public_catalog_url=public_catalog_url,
            expected_public_product_count=count,
            expected_public_snapshot_sha256=public_hash,
            expected_db_snapshot_sha256=db_hash,
            sources=sources,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _normalize_digest(value: Any, field: str) -> str:
        normalized = str(value or "").strip().lower()
        if not _SHA256_RE.fullmatch(normalized):
            raise ProductMediaUrlBackfillManifestError(f"{field} must be SHA-256")
        return normalized

    @staticmethod
    def _normalize_catalog_url(value: Any) -> str:
        normalized = str(value or "").strip()
        parsed = urlsplit(normalized)
        if (
            normalized != "https://api.mvn.by/api/v1/products"
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProductMediaUrlBackfillManifestError(
                "public_catalog_url must be the canonical MVN products endpoint"
            )
        return normalized

    @classmethod
    def _normalize_source(cls, payload: Any) -> ProductMediaUrlSourceRule:
        if not isinstance(payload, dict):
            raise ProductMediaUrlBackfillManifestError("Each source must be an object")
        allowed = {
            "old_url",
            "action",
            "expected_product_ids",
            "target_url",
            "fetch_url",
            "allowed_redirect_hosts",
            "rights_review_ref",
            "blocked_reason",
        }
        if not set(payload).issubset(allowed):
            raise ProductMediaUrlBackfillManifestError("Source contains unknown fields")
        old_url = str(payload.get("old_url") or "").strip()
        if not old_url or len(old_url) > 1000 or is_canonical_product_media_url(old_url):
            raise ProductMediaUrlBackfillManifestError("Source old_url is invalid")
        action = str(payload.get("action") or "").strip()
        if action not in {"reuse", "ingest", "blocked"}:
            raise ProductMediaUrlBackfillManifestError("Source action is invalid")
        raw_ids = payload.get("expected_product_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ProductMediaUrlBackfillManifestError(
                "Source expected_product_ids must be non-empty"
            )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in raw_ids):
            raise ProductMediaUrlBackfillManifestError("Source product ids are invalid")
        product_ids = tuple(sorted(set(raw_ids)))
        if len(product_ids) != len(raw_ids):
            raise ProductMediaUrlBackfillManifestError("Source product ids must be unique")

        target_url = cls._optional_string(payload.get("target_url"))
        fetch_url = cls._optional_string(payload.get("fetch_url"))
        redirect_hosts = cls._normalize_hosts(payload.get("allowed_redirect_hosts", []))
        rights_ref = cls._optional_string(payload.get("rights_review_ref"))
        blocked_reason = cls._optional_string(payload.get("blocked_reason"))
        if action == "reuse":
            if not target_url or not is_canonical_product_media_url(target_url):
                raise ProductMediaUrlBackfillManifestError(
                    "Reuse requires an exact canonical target_url"
                )
            if rights_ref or blocked_reason:
                raise ProductMediaUrlBackfillManifestError("Reuse has incompatible fields")
        elif action == "ingest":
            if target_url or blocked_reason:
                raise ProductMediaUrlBackfillManifestError("Ingest has incompatible fields")
            if fetch_url:
                cls._validate_https_source(fetch_url)
                source_host = str(urlsplit(fetch_url).hostname or "").lower()
                if source_host not in {"api.mvn.by", "cdn.mvn.by"} and not rights_ref:
                    raise ProductMediaUrlBackfillManifestError(
                        "External ingest requires rights_review_ref"
                    )
                if source_host not in redirect_hosts:
                    raise ProductMediaUrlBackfillManifestError(
                        "allowed_redirect_hosts must include the source host"
                    )
        else:
            if target_url or fetch_url or redirect_hosts or rights_ref or not blocked_reason:
                raise ProductMediaUrlBackfillManifestError("Blocked source fields are invalid")
        return ProductMediaUrlSourceRule(
            old_url=old_url,
            action=action,
            expected_product_ids=product_ids,
            target_url=target_url,
            fetch_url=fetch_url,
            allowed_redirect_hosts=redirect_hosts,
            rights_review_ref=rights_ref,
            blocked_reason=blocked_reason,
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or len(normalized) > 1000:
            raise ProductMediaUrlBackfillManifestError("Optional string is invalid")
        return normalized

    @staticmethod
    def _normalize_hosts(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or len(value) > 10:
            raise ProductMediaUrlBackfillManifestError("allowed_redirect_hosts is invalid")
        hosts = tuple(sorted({str(item or "").strip().lower() for item in value}))
        if any(
            not host
            or len(host) > 253
            or urlsplit(f"https://{host}").hostname != host
            or ":" in host
            for host in hosts
        ):
            raise ProductMediaUrlBackfillManifestError("Redirect host is invalid")
        return hosts

    @staticmethod
    def _validate_https_source(value: str) -> None:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.fragment
        ):
            raise ProductMediaUrlBackfillManifestError("fetch_url must be bounded HTTPS")

    @staticmethod
    def _source_payload(source: ProductMediaUrlSourceRule) -> dict[str, Any]:
        return {
            "old_url": source.old_url,
            "action": source.action,
            "expected_product_ids": list(source.expected_product_ids),
            "target_url": source.target_url,
            "fetch_url": source.fetch_url,
            "allowed_redirect_hosts": list(source.allowed_redirect_hosts),
            "rights_review_ref": source.rights_review_ref,
            "blocked_reason": source.blocked_reason,
        }


__all__ = [
    "ProductMediaUrlBackfillManifest",
    "ProductMediaUrlBackfillManifestError",
    "ProductMediaUrlSourceRule",
    "is_canonical_product_media_url",
]
