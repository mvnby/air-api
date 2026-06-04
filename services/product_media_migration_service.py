"""Migration helpers for moving product media variants to configured storage."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import ProductImage, ProductImageVariant
from services.media_storage_service import ProductMediaStorage
from services.product_image_processing_contract import (
    CATALOG_VARIANT_TYPES,
    ProductImageManualQualityStatus,
    ProductImageProcessingProvider,
    ProductImageProcessingStage,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_variant_service import ProductImageVariantService


DEFAULT_MIGRATION_VARIANT_TYPES = tuple(sorted(CATALOG_VARIANT_TYPES))


class ProductMediaMigrationService:
    @staticmethod
    async def migrate_to_storage(
        session: AsyncSession,
        *,
        storage: ProductMediaStorage,
        execute: bool,
        limit: int = 50,
        product_id: int | None = None,
        include_originals: bool = True,
        include_variants: bool = True,
        variant_types: list[str] | tuple[str, ...] | None = None,
        include_non_ready: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 1000))
        selected_variant_types = tuple(variant_types or DEFAULT_MIGRATION_VARIANT_TYPES)

        plan = await ProductMediaMigrationService.build_migration_plan(
            session,
            storage=storage,
            limit=safe_limit,
            product_id=product_id,
            include_originals=include_originals,
            include_variants=include_variants,
            variant_types=selected_variant_types,
            include_non_ready=include_non_ready,
            force=force,
        )
        plan["dry_run"] = not execute

        if not execute:
            return plan

        uploaded: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        now = datetime.now()

        for item in plan["items"]:
            source_path = Path(item["source_path"])
            try:
                content = source_path.read_bytes()
                stored = await storage.save_product_variant(
                    content=content,
                    variant_type=item["variant_type"],
                    extension=item["extension"],
                )
                variant = await ProductMediaMigrationService._resolve_target_variant(
                    session,
                    item=item,
                )
                variant.url = stored.url
                variant.storage_provider = stored.storage_provider
                variant.content_hash = stored.content_hash
                variant.updated_at = now

                if item["source_kind"] == "original":
                    variant.processing_status = ProductImageProcessingStatus.READY.value
                    variant.processing_stage = ProductImageProcessingStage.ORIGINAL_INGEST.value
                    variant.processing_provider = ProductImageProcessingProvider.MANUAL.value
                    variant.manual_quality_status = (
                        ProductImageManualQualityStatus.UNREVIEWED.value
                    )
                    variant.processing_error = None
                    variant.processed_at = variant.processed_at or now

                if variant.width is None or variant.height is None:
                    width, height = ProductImageVariantService._image_size(content)
                    variant.width = variant.width or width
                    variant.height = variant.height or height

                session.add(variant)
                uploaded.append(
                    {
                        **item,
                        "target_url": stored.url,
                        "target_path": stored.path,
                        "storage_provider": stored.storage_provider,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "source_kind": item["source_kind"],
                        "product_image_id": item["product_image_id"],
                        "variant_id": item.get("variant_id"),
                        "variant_type": item["variant_type"],
                        "source_url": item["source_url"],
                        "error": str(exc),
                    }
                )

        await session.commit()
        return {
            **plan,
            "uploaded": len(uploaded),
            "updated_variants": len(uploaded),
            "uploaded_items": uploaded,
            "errors": errors,
        }

    @staticmethod
    async def build_migration_plan(
        session: AsyncSession,
        *,
        storage: ProductMediaStorage,
        limit: int,
        product_id: int | None,
        include_originals: bool,
        include_variants: bool,
        variant_types: tuple[str, ...],
        include_non_ready: bool,
        force: bool,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        inspected = 0
        remaining = max(1, min(int(limit), 1000))

        if include_originals and remaining > 0:
            stmt = select(ProductImage).order_by(ProductImage.id).limit(remaining)
            if product_id is not None:
                stmt = stmt.where(ProductImage.product_id == product_id)
            rows = (await session.execute(stmt)).scalars().all()
            inspected += len(rows)
            for image in rows:
                existing = await ProductMediaMigrationService._get_variant(
                    session,
                    product_image_id=image.id,
                    variant_type=ProductImageVariantType.ORIGINAL.value,
                )
                item = ProductMediaMigrationService._plan_item(
                    storage=storage,
                    source_kind="original",
                    product_image_id=image.id,
                    product_id=image.product_id,
                    variant_type=ProductImageVariantType.ORIGINAL.value,
                    source_url=image.url,
                    variant=existing,
                    force=force,
                )
                if item["planned"]:
                    items.append(item)
                else:
                    skipped.append(item)
            remaining -= len(rows)

        if include_variants and remaining > 0:
            stmt = (
                select(ProductImageVariant, ProductImage)
                .join(ProductImage, ProductImage.id == ProductImageVariant.product_image_id)
                .where(ProductImageVariant.url.is_not(None))
                .where(ProductImageVariant.variant_type.in_(variant_types))
                .order_by(ProductImageVariant.id)
                .limit(remaining)
            )
            if product_id is not None:
                stmt = stmt.where(ProductImage.product_id == product_id)
            if not include_non_ready:
                stmt = stmt.where(
                    ProductImageVariant.processing_status
                    == ProductImageProcessingStatus.READY.value
                )

            rows = (await session.execute(stmt)).all()
            inspected += len(rows)
            for variant, image in rows:
                item = ProductMediaMigrationService._plan_item(
                    storage=storage,
                    source_kind="variant",
                    product_image_id=image.id,
                    product_id=image.product_id,
                    variant_type=variant.variant_type,
                    source_url=variant.url,
                    variant=variant,
                    force=force,
                )
                if item["planned"]:
                    items.append(item)
                else:
                    skipped.append(item)

        return {
            "dry_run": True,
            "storage_provider": storage.provider_name,
            "limit": limit,
            "product_id": product_id,
            "include_originals": include_originals,
            "include_variants": include_variants,
            "variant_types": list(variant_types),
            "include_non_ready": include_non_ready,
            "force": force,
            "inspected": inspected,
            "planned_uploads": len(items),
            "skipped_count": len(skipped),
            "items": items,
            "skipped": skipped,
            "uploaded": 0,
            "updated_variants": 0,
            "uploaded_items": [],
            "errors": [],
        }

    @staticmethod
    def _plan_item(
        *,
        storage: ProductMediaStorage,
        source_kind: str,
        product_image_id: int,
        product_id: int,
        variant_type: str,
        source_url: str | None,
        variant: ProductImageVariant | None,
        force: bool,
    ) -> dict[str, Any]:
        base = {
            "planned": False,
            "source_kind": source_kind,
            "product_image_id": product_image_id,
            "product_id": product_id,
            "variant_id": variant.id if variant else None,
            "variant_type": variant_type,
            "source_url": source_url,
            "current_storage_provider": variant.storage_provider if variant else None,
            "current_variant_url": variant.url if variant else None,
        }

        if (
            variant
            and not force
            and variant.storage_provider == storage.provider_name
            and variant.url
        ):
            return {**base, "skip_reason": "already_on_target_provider"}

        source_path = ProductImageVariantService._local_media_path_for_url(source_url or "")
        if source_path is None:
            return {**base, "skip_reason": "non_local_url"}
        if not source_path.exists():
            return {
                **base,
                "source_path": str(source_path),
                "skip_reason": "missing_local_file",
            }

        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        extension = source_path.suffix.lower().lstrip(".") or "webp"
        target = storage.build_product_variant_object(
            content_hash=content_hash,
            variant_type=variant_type,
            extension=extension,
        )
        return {
            **base,
            "planned": True,
            "source_path": str(source_path),
            "extension": extension,
            "content_hash": content_hash,
            "target_url": target.url,
            "target_path": target.path,
            "target_storage_provider": target.storage_provider,
        }

    @staticmethod
    async def _resolve_target_variant(
        session: AsyncSession,
        *,
        item: dict[str, Any],
    ) -> ProductImageVariant:
        if item.get("variant_id"):
            variant = await session.get(ProductImageVariant, item["variant_id"])
            if variant:
                return variant

        return await ProductImageVariantService._get_or_create_variant(
            session,
            product_image_id=item["product_image_id"],
            variant_type=item["variant_type"],
        )

    @staticmethod
    async def _get_variant(
        session: AsyncSession,
        *,
        product_image_id: int,
        variant_type: str,
    ) -> ProductImageVariant | None:
        return (
            await session.execute(
                select(ProductImageVariant).where(
                    ProductImageVariant.product_image_id == product_image_id,
                    ProductImageVariant.variant_type == variant_type,
                )
            )
        ).scalar_one_or_none()
