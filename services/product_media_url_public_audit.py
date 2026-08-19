"""Read-only canonical public-catalog snapshot used by media repair plans."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from services.product_media_url_backfill_manifest import (
    ProductMediaUrlBackfillManifest,
    is_canonical_product_media_url,
)


class ProductMediaUrlPublicAuditError(RuntimeError):
    pass


class ProductMediaUrlPublicAudit:
    PAGE_SIZE = 100
    MAX_PAGES = 1000
    TIMEOUT_SECONDS = 20.0

    @classmethod
    async def run(
        cls,
        manifest: ProductMediaUrlBackfillManifest,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        owns_client = client is None
        active_client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(cls.TIMEOUT_SECONDS),
            follow_redirects=False,
            headers={"User-Agent": "MVN product-media public audit/1"},
        )
        items: list[dict[str, Any]] = []
        expected_total: int | None = None
        try:
            page = 1
            while True:
                response = await active_client.get(
                    manifest.public_catalog_url,
                    params={"limit": cls.PAGE_SIZE, "page": page},
                )
                if response.status_code != 200:
                    raise ProductMediaUrlPublicAuditError(
                        f"Public catalog page {page} returned HTTP {response.status_code}"
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProductMediaUrlPublicAuditError(
                        "Public catalog returned invalid JSON"
                    ) from exc
                page_items, total, pages = cls._validate_page(payload, page)
                if expected_total is None:
                    expected_total = total
                elif total != expected_total:
                    raise ProductMediaUrlPublicAuditError(
                        "Public catalog total changed during pagination"
                    )
                items.extend(page_items)
                if page >= pages:
                    break
                page += 1
                if page > cls.MAX_PAGES:
                    raise ProductMediaUrlPublicAuditError(
                        "Public catalog exceeded the pagination safety limit"
                    )
        except httpx.HTTPError as exc:
            raise ProductMediaUrlPublicAuditError(
                "Public catalog request failed"
            ) from exc
        finally:
            if owns_client:
                await active_client.aclose()

        ids = [int(item["id"]) for item in items]
        if len(ids) != len(set(ids)) or len(items) != expected_total:
            raise ProductMediaUrlPublicAuditError(
                "Public catalog pagination is incomplete or duplicated"
            )
        snapshot = [
            {
                "id": int(item["id"]),
                "slug": str(item.get("slug") or ""),
                "main_image": item.get("main_image"),
                "card_image": item.get("card_image"),
                "full_image": item.get("full_image"),
            }
            for item in sorted(items, key=lambda value: int(value["id"]))
        ]
        snapshot_hash = hashlib.sha256(
            json.dumps(
                snapshot,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        blocked: list[dict[str, Any]] = []
        for item in snapshot:
            for field in ("main_image", "card_image", "full_image"):
                url = str(item.get(field) or "").strip()
                if url and not is_canonical_product_media_url(url):
                    blocked.append(
                        {
                            "product_id": item["id"],
                            "slug": item["slug"],
                            "field": field,
                            "url": url,
                        }
                    )
        return {
            "product_count": len(snapshot),
            "snapshot_sha256": snapshot_hash,
            "blocked_field_count": len(blocked),
            "blocked_product_count": len(
                {int(item["product_id"]) for item in blocked}
            ),
            "blocked": blocked,
            "items": snapshot,
        }

    @classmethod
    async def run_reviewed(
        cls,
        manifest: ProductMediaUrlBackfillManifest,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        audit = await cls.run(manifest, client=client)
        source_urls = {source.old_url for source in manifest.sources}
        unmatched = sorted(
            {
                item["url"]
                for item in audit["blocked"]
                if item["url"] not in source_urls
            }
        )
        actual_products_by_source: dict[str, set[int]] = {}
        for item in audit["blocked"]:
            actual_products_by_source.setdefault(str(item["url"]), set()).add(
                int(item["product_id"])
            )
        source_drift = []
        for source in manifest.sources:
            actual = tuple(
                sorted(actual_products_by_source.get(source.old_url, set()))
            )
            if actual != source.expected_product_ids:
                source_drift.append(
                    {
                        "old_url": source.old_url,
                        "expected_product_ids": list(source.expected_product_ids),
                        "actual_product_ids": list(actual),
                    }
                )
        return {
            **{key: value for key, value in audit.items() if key != "items"},
            "expected_product_count": manifest.expected_public_product_count,
            "expected_snapshot_sha256": manifest.expected_public_snapshot_sha256,
            "snapshot_matches": (
                audit["product_count"] == manifest.expected_public_product_count
                and audit["snapshot_sha256"]
                == manifest.expected_public_snapshot_sha256
            ),
            "manifest_source_count": len(manifest.sources),
            "unmatched_blocked_urls": unmatched,
            "source_product_drift": source_drift,
        }

    @staticmethod
    def _validate_page(
        payload: Any,
        requested_page: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProductMediaUrlPublicAuditError("Public catalog page shape is invalid")
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            raise ProductMediaUrlPublicAuditError("Public catalog metadata is missing")
        total = meta.get("total")
        page = meta.get("page")
        pages = meta.get("pages")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (total, page, pages)):
            raise ProductMediaUrlPublicAuditError("Public catalog pagination metadata is invalid")
        if total < 0 or page != requested_page or pages < 1 or requested_page > pages:
            raise ProductMediaUrlPublicAuditError("Public catalog pagination metadata drifted")
        for item in payload["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                raise ProductMediaUrlPublicAuditError("Public catalog item is invalid")
        return payload["items"], total, pages


__all__ = ["ProductMediaUrlPublicAudit", "ProductMediaUrlPublicAuditError"]
