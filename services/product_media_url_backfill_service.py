"""Plan and atomically apply exact product-media URL repairs."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.catalog_mutation_contracts import require_global_catalog_mutation_contract
from services.catalog_revision_service import CatalogRevisionService
from services.media_storage_service import (
    ProductOriginalSourceStorage,
    get_product_original_source_storage,
)
from services.product_media_url_backfill_download import (
    BoundedProductMediaDownloader,
    ProductMediaDownloadBlockedError,
)
from services.product_media_url_backfill_manifest import (
    ProductMediaUrlBackfillManifest,
    ProductMediaUrlSourceRule,
    is_canonical_product_media_url,
)
from services.product_media_url_backfill_plan_token import (
    ProductMediaUrlBackfillBlockedError,
    ProductMediaUrlBackfillPlanToken,
)
from services.product_media_url_backfill_state import (
    LoadedProductMediaUrlState,
    apply_product_media_url_locations,
    collect_product_media_url_locations,
    detect_product_media_url_collisions,
    load_product_media_url_state,
    product_media_url_db_snapshot_hash,
    product_media_url_targets_are_complete,
)
from services.product_media_url_public_audit import ProductMediaUrlPublicAudit
from services.product_original_media_service import ProductOriginalMediaService


class ProductMediaUrlBackfillService:
    LOCK_NAME = "mvn:product-media-url-backfill:v1"

    @classmethod
    async def audit_public(
        cls,
        manifest: ProductMediaUrlBackfillManifest,
        *,
        public_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        return await ProductMediaUrlPublicAudit.run_reviewed(
            manifest,
            client=public_client,
        )

    @classmethod
    async def verify_public_residual(
        cls,
        manifest: ProductMediaUrlBackfillManifest,
        *,
        public_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        audit = await ProductMediaUrlPublicAudit.run(
            manifest,
            client=public_client,
        )
        expected = sorted(
            (
                product_id,
                field,
                source.old_url,
            )
            for source in manifest.sources
            if source.action == "blocked"
            for product_id in source.expected_product_ids
            for field in ("card_image", "full_image", "main_image")
        )
        actual = sorted(
            (
                int(item["product_id"]),
                str(item["field"]),
                str(item["url"]),
            )
            for item in audit["blocked"]
        )
        residual_matches = (
            audit["product_count"] == manifest.expected_public_product_count
            and actual == expected
        )
        return {
            "verified": residual_matches,
            "product_count": audit["product_count"],
            "expected_product_count": manifest.expected_public_product_count,
            "blocked_product_count": audit["blocked_product_count"],
            "blocked_field_count": audit["blocked_field_count"],
            "expected_blocked_product_ids": sorted(
                {
                    product_id
                    for source in manifest.sources
                    if source.action == "blocked"
                    for product_id in source.expected_product_ids
                }
            ),
            "expected_blocked_field_count": len(expected),
            "unexpected_or_missing_residuals": [
                {"product_id": item[0], "field": item[1], "url": item[2]}
                for item in sorted(set(actual) ^ set(expected))
            ],
        }

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        manifest: ProductMediaUrlBackfillManifest,
        public_client: httpx.AsyncClient | None = None,
        downloader: BoundedProductMediaDownloader | None = None,
        source_storage: ProductOriginalSourceStorage | None = None,
    ) -> dict[str, Any]:
        public_audit = await cls.audit_public(manifest, public_client=public_client)
        state = await cls._load_state(session, for_update=False)
        return await cls._build_plan(
            manifest=manifest,
            public_audit=public_audit,
            state=state,
            downloader=downloader or BoundedProductMediaDownloader(),
            source_storage=source_storage or get_product_original_source_storage(
                require_write=False
            ),
            issue_token=True,
        )

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        manifest: ProductMediaUrlBackfillManifest,
        plan_token: str,
        public_client: httpx.AsyncClient | None = None,
        downloader: BoundedProductMediaDownloader | None = None,
        source_storage: ProductOriginalSourceStorage | None = None,
    ) -> dict[str, Any]:
        verified = ProductMediaUrlBackfillPlanToken.verify(plan_token)
        active_downloader = downloader or BoundedProductMediaDownloader()
        active_storage = source_storage or get_product_original_source_storage(
            require_write=True
        )
        public_audit = await cls.audit_public(manifest, public_client=public_client)
        await cls._require_primary_and_lock(session)
        state = await cls._load_state(session, for_update=True)
        reviewed = await cls._build_plan(
            manifest=manifest,
            public_audit=public_audit,
            state=state,
            downloader=active_downloader,
            source_storage=active_storage,
            issue_token=False,
        )
        if not hmac.compare_digest(verified.plan_digest, reviewed["plan_digest"]):
            raise ProductMediaUrlBackfillBlockedError(
                "Media repair plan is stale; run a fresh plan"
            )
        if not reviewed["ready"]:
            raise ProductMediaUrlBackfillBlockedError(
                "Media repair is blocked: " + "; ".join(reviewed["blockers"])
            )
        if reviewed["complete"]:
            return {
                "mode": "execute",
                "changed": False,
                "complete": True,
                "executable_complete": True,
                "presentation_complete": reviewed["presentation_complete"],
                "reviewed_plan_digest": reviewed["plan_digest"],
                "changed_product_count": 0,
                "changed_location_count": 0,
                "changes": [],
                "source_evidence": reviewed["source_evidence"],
                "deferred_sources": reviewed["deferred_sources"],
                "requires_post_commit_public_verification": True,
            }

        target_by_source: dict[str, str] = {}
        evidence_by_source = {
            item["old_url"]: item for item in reviewed["source_evidence"]
        }
        for source in manifest.sources:
            if source.action == "blocked":
                continue
            evidence = evidence_by_source[source.old_url]
            if source.action == "reuse":
                target_by_source[source.old_url] = str(source.target_url)
                continue
            downloaded = await active_downloader.download(
                evidence["fetch_url"],
                allowed_hosts=tuple(evidence["allowed_hosts"]),
            )
            if not hmac.compare_digest(downloaded.content_hash, evidence["source_content_hash"]):
                raise ProductMediaUrlBackfillBlockedError(
                    "Image source changed after the reviewed plan"
                )
            ingested = await ProductOriginalMediaService.save_shared_original(
                downloaded.content,
                source_storage=active_storage,
            )
            if not is_canonical_product_media_url(ingested.url):
                raise ProductMediaUrlBackfillBlockedError(
                    "Configured media storage did not return a canonical public URL"
                )
            if not hmac.compare_digest(ingested.content_hash, evidence["target_content_hash"]):
                raise ProductMediaUrlBackfillBlockedError(
                    "Ingested media hash differs from the reviewed target"
                )
            if ingested.url != evidence["target_url"]:
                raise ProductMediaUrlBackfillBlockedError(
                    "Ingested media target differs from the reviewed target"
                )
            target_by_source[source.old_url] = ingested.url

        changes = apply_product_media_url_locations(
            state,
            locations=reviewed["locations"],
            target_by_source=target_by_source,
        )
        changed_product_ids = sorted({int(item["product_id"]) for item in changes})
        if changes:
            contract = require_global_catalog_mutation_contract(
                "product_media_url.backfill"
            )
            await CatalogRevisionService.stage_invalidation(
                session,
                reason=contract.reason,
                product_ids=changed_product_ids,
            )
        return {
            "mode": "execute",
            "changed": bool(changes),
            "complete": True,
            "executable_complete": True,
            "presentation_complete": not reviewed["deferred_sources"],
            "reviewed_plan_digest": reviewed["plan_digest"],
            "execution_id": "media-url-" + hashlib.sha256(
                plan_token.encode("utf-8")
            ).hexdigest()[:32],
            "changed_product_count": len(changed_product_ids),
            "changed_location_count": len(changes),
            "changes": changes,
            "source_evidence": reviewed["source_evidence"],
            "deferred_sources": reviewed["deferred_sources"],
            "requires_post_commit_public_verification": True,
        }

    @classmethod
    async def _build_plan(
        cls,
        *,
        manifest: ProductMediaUrlBackfillManifest,
        public_audit: dict[str, Any],
        state: LoadedProductMediaUrlState,
        downloader: BoundedProductMediaDownloader,
        source_storage: ProductOriginalSourceStorage,
        issue_token: bool,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        if public_audit["unmatched_blocked_urls"]:
            blockers.append("public audit contains blocked URLs outside the manifest")
        if public_audit["source_product_drift"]:
            blockers.append("public product/source membership drifted")
        db_snapshot_hash = product_media_url_db_snapshot_hash(state.products)
        if not hmac.compare_digest(db_snapshot_hash, manifest.expected_db_snapshot_sha256):
            blockers.append("published product DB snapshot drifted")
        if not public_audit["snapshot_matches"]:
            blockers.append("public catalog snapshot drifted")

        locations = collect_product_media_url_locations(state, manifest)
        for source in manifest.sources:
            for product_id in source.expected_product_ids:
                product = state.products_by_id.get(product_id)
                if product is None or product.main_image != source.old_url:
                    blockers.append(
                        f"expected product#{product_id} main image drifted for {source.old_url}"
                    )
        source_evidence: list[dict[str, Any]] = []
        deferred_sources: list[dict[str, Any]] = []
        for source in manifest.sources:
            if source.action == "blocked":
                deferred = {
                    "old_url": source.old_url,
                    "action": source.action,
                    "product_ids": list(source.expected_product_ids),
                    "blocked_reason": source.blocked_reason,
                }
                source_evidence.append(deferred)
                deferred_sources.append(deferred)
                continue
            try:
                evidence = await cls._resolve_source_evidence(
                    source,
                    downloader=downloader,
                    source_storage=source_storage,
                )
            except (ProductMediaDownloadBlockedError, ValueError, OSError) as exc:
                blockers.append(f"{source.old_url}: {exc}")
                evidence = {
                    "old_url": source.old_url,
                    "action": source.action,
                    "product_ids": list(source.expected_product_ids),
                    "error": str(exc),
                }
            source_evidence.append(evidence)

        target_by_source = {
            str(item["old_url"]): (
                str(item["target_url"]) if item.get("target_url") else None
            )
            for item in source_evidence
        }
        detect_product_media_url_collisions(
            state,
            manifest,
            target_by_source,
            blockers,
        )

        complete = False
        if not locations:
            complete = product_media_url_targets_are_complete(
                state,
                manifest,
                target_by_source,
            )
            if complete:
                blockers = [
                    item
                    for item in blockers
                    if item not in {
                        "published product DB snapshot drifted",
                        "public catalog snapshot drifted",
                        "public product/source membership drifted",
                    }
                    and not item.startswith("expected product#")
                ]
        plan_payload = {
            "manifest_fingerprint": manifest.fingerprint,
            "public_snapshot_sha256": public_audit["snapshot_sha256"],
            "db_snapshot_sha256": db_snapshot_hash,
            "locations": locations,
            "source_evidence": source_evidence,
            "deferred_sources": deferred_sources,
            "blockers": sorted(set(blockers)),
            "complete": complete,
        }
        plan_digest = hashlib.sha256(
            json.dumps(
                plan_payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        ready = not blockers
        presentation_complete = complete and not deferred_sources
        result = {
            "mode": "plan",
            "manifest_name": manifest.name,
            "manifest_fingerprint": manifest.fingerprint,
            "public_audit": public_audit,
            "db_snapshot_sha256": db_snapshot_hash,
            "expected_db_snapshot_sha256": manifest.expected_db_snapshot_sha256,
            "location_count": len(locations),
            "product_count": len({item["product_id"] for item in locations}),
            "locations": locations,
            "source_evidence": source_evidence,
            "deferred_source_count": len(deferred_sources),
            "deferred_product_count": len(
                {
                    product_id
                    for source in manifest.sources
                    if source.action == "blocked"
                    for product_id in source.expected_product_ids
                }
            ),
            "deferred_sources": deferred_sources,
            "blockers": sorted(set(blockers)),
            "ready": ready,
            "complete": complete,
            "executable_complete": complete,
            "presentation_complete": presentation_complete,
            "plan_digest": plan_digest,
        }
        if issue_token and ready:
            result["plan_token"] = ProductMediaUrlBackfillPlanToken.issue(
                plan_digest=plan_digest
            )
            result["plan_token_max_age_seconds"] = (
                ProductMediaUrlBackfillPlanToken.MAX_AGE_SECONDS
            )
        return result

    @classmethod
    async def _resolve_source_evidence(
        cls,
        source: ProductMediaUrlSourceRule,
        *,
        downloader: BoundedProductMediaDownloader,
        source_storage: ProductOriginalSourceStorage,
    ) -> dict[str, Any]:
        fetch_url, allowed_hosts = cls._fetch_boundary(source)
        downloaded = await downloader.download(fetch_url, allowed_hosts=allowed_hosts)
        base = {
            "old_url": source.old_url,
            "action": source.action,
            "product_ids": list(source.expected_product_ids),
            "fetch_url": fetch_url,
            "final_url": downloaded.final_url,
            "allowed_hosts": list(allowed_hosts),
            "source_content_type": downloaded.content_type,
            "source_content_hash": downloaded.content_hash,
            "source_size_bytes": len(downloaded.content),
            "width": downloaded.width,
            "height": downloaded.height,
        }
        if source.action == "reuse":
            target = await downloader.download(
                str(source.target_url),
                allowed_hosts=("cdn.mvn.by",),
            )
            if not hmac.compare_digest(downloaded.content_hash, target.content_hash):
                raise ProductMediaDownloadBlockedError(
                    "Existing canonical target content does not match its source"
                )
            return {
                **base,
                "target_url": source.target_url,
                "target_content_hash": target.content_hash,
                "target_size_bytes": len(target.content),
            }
        webp_content, width, height = await ProductOriginalMediaService.to_webp_bytes(
            downloaded.content
        )
        target_hash = hashlib.sha256(webp_content).hexdigest()
        target = source_storage.build_product_original_object(
            content_hash=target_hash,
            extension="webp",
        )
        if not is_canonical_product_media_url(target.url):
            raise ProductMediaDownloadBlockedError(
                "Configured original media target is outside the presentation allowlist"
            )
        return {
            **base,
            "target_url": target.url,
            "target_content_hash": target_hash,
            "target_size_bytes": len(webp_content),
            "target_width": width,
            "target_height": height,
            "target_storage_provider": target.storage_provider,
            "target_storage_path": target.path,
            "rights_review_ref": source.rights_review_ref,
        }

    @staticmethod
    def _fetch_boundary(source: ProductMediaUrlSourceRule) -> tuple[str, tuple[str, ...]]:
        if source.fetch_url:
            return source.fetch_url, source.allowed_redirect_hosts
        old = source.old_url
        parsed = urlsplit(old)
        if parsed.scheme == "https":
            host = str(parsed.hostname or "").lower()
            if host not in {"api.mvn.by", "cdn.mvn.by"}:
                raise ProductMediaDownloadBlockedError(
                    "External source needs an explicit reviewed fetch boundary"
                )
            return old, (host,)
        if parsed.scheme or parsed.netloc or "?" in old or "#" in old:
            raise ProductMediaDownloadBlockedError("Legacy source path is invalid")
        normalized_path = "/" + old.lstrip("/")
        if not normalized_path.startswith("/media/products/") or ".." in normalized_path:
            raise ProductMediaDownloadBlockedError(
                "Legacy source is outside /media/products"
            )
        return f"https://api.mvn.by{normalized_path}", ("api.mvn.by",)

    @classmethod
    async def _require_primary_and_lock(cls, session: AsyncSession) -> None:
        if session.bind is None or session.bind.dialect.name != "postgresql":
            raise ProductMediaUrlBackfillBlockedError(
                "Execute is supported only on PostgreSQL primary"
            )
        in_recovery = bool(
            (await session.execute(text("SELECT pg_is_in_recovery()"))).scalar_one()
        )
        if in_recovery:
            raise ProductMediaUrlBackfillBlockedError(
                "Media repair cannot run on a PostgreSQL standby"
            )
        acquired = bool(
            (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_name))"),
                    {"lock_name": cls.LOCK_NAME},
                )
            ).scalar_one()
        )
        if not acquired:
            raise ProductMediaUrlBackfillBlockedError(
                "Another product-media repair owns the advisory lock"
            )

    # Compatibility aliases keep the safety-critical facade stable for callers and tests.
    _load_state = staticmethod(load_product_media_url_state)
    _db_snapshot_hash = staticmethod(product_media_url_db_snapshot_hash)


__all__ = ["ProductMediaUrlBackfillService"]
