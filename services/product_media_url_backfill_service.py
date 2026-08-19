"""Plan and atomically apply exact product-media URL repairs."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ProductImage, ProductImageVariant
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
from services.product_media_url_public_audit import ProductMediaUrlPublicAudit
from services.product_original_media_service import ProductOriginalMediaService


@dataclass(slots=True)
class _LoadedProductState:
    products: list[Product]
    products_by_id: dict[int, Product]
    image_by_id: dict[int, ProductImage]
    variant_by_id: dict[int, ProductImageVariant]


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
                "reviewed_plan_digest": reviewed["plan_digest"],
                "changed_product_count": 0,
                "changed_location_count": 0,
                "changes": [],
                "source_evidence": reviewed["source_evidence"],
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

        changes = cls._apply_locations(
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
            "reviewed_plan_digest": reviewed["plan_digest"],
            "execution_id": "media-url-" + hashlib.sha256(
                plan_token.encode("utf-8")
            ).hexdigest()[:32],
            "changed_product_count": len(changed_product_ids),
            "changed_location_count": len(changes),
            "changes": changes,
            "source_evidence": reviewed["source_evidence"],
        }

    @classmethod
    async def _build_plan(
        cls,
        *,
        manifest: ProductMediaUrlBackfillManifest,
        public_audit: dict[str, Any],
        state: _LoadedProductState,
        downloader: BoundedProductMediaDownloader,
        source_storage: ProductOriginalSourceStorage,
        issue_token: bool,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        if public_audit["unmatched_blocked_urls"]:
            blockers.append("public audit contains blocked URLs outside the manifest")
        if public_audit["source_product_drift"]:
            blockers.append("public product/source membership drifted")
        db_snapshot_hash = cls._db_snapshot_hash(state.products)
        if not hmac.compare_digest(db_snapshot_hash, manifest.expected_db_snapshot_sha256):
            blockers.append("published product DB snapshot drifted")
        if not public_audit["snapshot_matches"]:
            blockers.append("public catalog snapshot drifted")

        locations = cls._collect_locations(state, manifest)
        for source in manifest.sources:
            for product_id in source.expected_product_ids:
                product = state.products_by_id.get(product_id)
                if product is None or product.main_image != source.old_url:
                    blockers.append(
                        f"expected product#{product_id} main image drifted for {source.old_url}"
                    )
        cls._detect_product_image_collisions(state, manifest, blockers)

        source_evidence: list[dict[str, Any]] = []
        for source in manifest.sources:
            if source.action == "blocked":
                blockers.append(
                    f"{source.old_url}: {source.blocked_reason or 'review required'}"
                )
                source_evidence.append(
                    {
                        "old_url": source.old_url,
                        "action": source.action,
                        "product_ids": list(source.expected_product_ids),
                        "blocked_reason": source.blocked_reason,
                    }
                )
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

        complete = False
        if not locations and not any(source.action == "blocked" for source in manifest.sources):
            target_by_source = {
                item["old_url"]: item.get("target_url") for item in source_evidence
            }
            complete = cls._targets_are_complete(state, manifest, target_by_source)
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
            "blockers": sorted(set(blockers)),
            "ready": ready,
            "complete": complete,
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

    @staticmethod
    async def _load_state(
        session: AsyncSession,
        *,
        for_update: bool,
    ) -> _LoadedProductState:
        stmt = (
            select(Product)
            .where(Product.is_published.is_(True))
            .options(
                selectinload(Product.gallery_images).selectinload(
                    ProductImage.variants
                )
            )
            .order_by(Product.id.asc())
        )
        if for_update:
            stmt = stmt.with_for_update()
        products = list((await session.execute(stmt)).scalars().unique().all())
        if for_update:
            product_ids = [int(product.id) for product in products]
            if product_ids:
                list(
                    (
                        await session.execute(
                            select(ProductImage)
                            .where(ProductImage.product_id.in_(product_ids))
                            .order_by(ProductImage.id.asc())
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).scalars()
                )
                image_ids = [
                    int(image.id)
                    for product in products
                    for image in product.gallery_images or []
                    if image.id is not None
                ]
                if image_ids:
                    list(
                        (
                            await session.execute(
                                select(ProductImageVariant)
                                .where(
                                    ProductImageVariant.product_image_id.in_(image_ids)
                                )
                                .order_by(ProductImageVariant.id.asc())
                                .with_for_update()
                                .execution_options(populate_existing=True)
                            )
                        ).scalars()
                    )
        images = {
            int(image.id): image
            for product in products
            for image in product.gallery_images or []
            if image.id is not None
        }
        variants = {
            int(variant.id): variant
            for image in images.values()
            for variant in image.variants or []
            if variant.id is not None
        }
        return _LoadedProductState(
            products=products,
            products_by_id={int(product.id): product for product in products},
            image_by_id=images,
            variant_by_id=variants,
        )

    @staticmethod
    def _db_snapshot_hash(products: list[Product]) -> str:
        payload = [
            {
                "id": int(product.id),
                "slug": str(product.slug),
                "main_image": product.main_image,
            }
            for product in products
        ]
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _collect_locations(
        state: _LoadedProductState,
        manifest: ProductMediaUrlBackfillManifest,
    ) -> list[dict[str, Any]]:
        source_by_product_id = {
            product_id: source.old_url
            for source in manifest.sources
            for product_id in source.expected_product_ids
        }
        locations: list[dict[str, Any]] = []
        for product in state.products:
            product_id = int(product.id)
            source_url = source_by_product_id.get(product_id)
            if source_url is None:
                continue
            if product.main_image == source_url:
                locations.append(
                    cls_location("product", product_id, product_id, "main_image", None, product.main_image)
                )
            images = list(product.images or [])
            for index, value in enumerate(images):
                if value == source_url:
                    locations.append(
                        cls_location("product", product_id, product_id, "images", index, value)
                    )
            for image in product.gallery_images or []:
                if image.url == source_url:
                    locations.append(
                        cls_location("product_image", int(image.id), product_id, "url", None, image.url)
                    )
                for variant in image.variants or []:
                    if variant.url == source_url:
                        locations.append(
                            cls_location(
                                "product_image_variant",
                                int(variant.id),
                                product_id,
                                "url",
                                None,
                                variant.url,
                            )
                        )
        return sorted(
            locations,
            key=lambda item: (
                item["product_id"],
                item["table"],
                item["row_id"],
                item["field"],
                -1 if item["index"] is None else item["index"],
            ),
        )

    @staticmethod
    def _detect_product_image_collisions(
        state: _LoadedProductState,
        manifest: ProductMediaUrlBackfillManifest,
        blockers: list[str],
    ) -> None:
        target_by_source = {
            source.old_url: source.target_url
            for source in manifest.sources
            if source.action == "reuse"
        }
        expected_ids = {
            product_id
            for source in manifest.sources
            for product_id in source.expected_product_ids
        }
        for product in state.products:
            if int(product.id) not in expected_ids:
                continue
            urls = {image.url for image in product.gallery_images or []}
            for image in product.gallery_images or []:
                target = target_by_source.get(image.url)
                if target and target != image.url and target in urls:
                    blockers.append(
                        f"product#{product.id} already has ProductImage target {target}"
                    )

    @staticmethod
    def _targets_are_complete(
        state: _LoadedProductState,
        manifest: ProductMediaUrlBackfillManifest,
        target_by_source: dict[str, str | None],
    ) -> bool:
        for source in manifest.sources:
            target = target_by_source.get(source.old_url)
            if not target:
                return False
            for product_id in source.expected_product_ids:
                product = state.products_by_id.get(product_id)
                if product is None or product.main_image != target:
                    return False
        return True

    @staticmethod
    def _apply_locations(
        state: _LoadedProductState,
        *,
        locations: list[dict[str, Any]],
        target_by_source: dict[str, str],
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for location in locations:
            before = location["old_url"]
            target = target_by_source.get(before)
            if not target:
                raise ProductMediaUrlBackfillBlockedError(
                    "Reviewed target is missing for a planned location"
                )
            table = location["table"]
            row_id = int(location["row_id"])
            if table == "product":
                row = state.products_by_id[row_id]
                if location["field"] == "main_image":
                    if row.main_image != before:
                        raise ProductMediaUrlBackfillBlockedError(
                            "Product main image changed after planning"
                        )
                    row.main_image = target
                else:
                    values = list(row.images or [])
                    index = int(location["index"])
                    if index >= len(values) or values[index] != before:
                        raise ProductMediaUrlBackfillBlockedError(
                            "Product image list changed after planning"
                        )
                    values[index] = target
                    row.images = values
            elif table == "product_image":
                row = state.image_by_id[row_id]
                if row.url != before:
                    raise ProductMediaUrlBackfillBlockedError(
                        "ProductImage changed after planning"
                    )
                row.url = target
            else:
                row = state.variant_by_id[row_id]
                if row.url != before:
                    raise ProductMediaUrlBackfillBlockedError(
                        "ProductImageVariant changed after planning"
                    )
                row.url = target
            changes.append({**location, "new_url": target})
        return changes

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


def cls_location(
    table: str,
    row_id: int,
    product_id: int,
    field: str,
    index: int | None,
    old_url: str,
) -> dict[str, Any]:
    return {
        "table": table,
        "row_id": row_id,
        "product_id": product_id,
        "field": field,
        "index": index,
        "old_url": old_url,
    }


__all__ = ["ProductMediaUrlBackfillService"]
