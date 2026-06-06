"""Service layer for manager-approved product main-image cleanup."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_main_image_cleanup import ProductMainImageCleanupDAO
from models import Product, ProductMainImageCleanupBatch, ProductMainImageCleanupItem
from services.catalog_revision_service import CatalogRevisionService
from services.media_storage_service import ProductMediaStorage, get_product_media_storage
from services.product_main_image_cleanup_contract import (
    MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
    ProductMainImageCleanupSkipReason,
    ProductMainImageCleanupStatus,
    normalize_cleanup_processor,
)
from services.product_main_image_cleanup_provider import (
    ProductMainImageCleanupContext,
    ProductMainImageCleanupProcessorAdapter,
    get_main_image_cleanup_processor,
)


class ProductMainImageCleanupService:
    @staticmethod
    async def create_batch(
        session: AsyncSession,
        *,
        limit: int = 50,
        processor_method: str = "noop",
        created_by: str | None = None,
        storage: ProductMediaStorage | None = None,
        processor: ProductMainImageCleanupProcessorAdapter | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        normalized_processor = normalize_cleanup_processor(processor_method)
        active_processor = processor or get_main_image_cleanup_processor(normalized_processor)
        active_storage = storage or get_product_media_storage()
        now = datetime.now()

        batch = ProductMainImageCleanupBatch(
            status=ProductMainImageCleanupStatus.PROCESSING.value,
            requested_limit=safe_limit,
            processor_method=active_processor.processor_method,
            processor_version=active_processor.processor_version,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(batch)
        await session.flush()

        items: list[ProductMainImageCleanupItem] = []
        skipped_existing: list[dict[str, Any]] = []
        products = await ProductMainImageCleanupDAO.list_products_with_main_images(session)

        for product in products:
            if len(items) >= safe_limit:
                break
            if product.id is None:
                continue
            source_url = product.main_image
            if not source_url:
                item = ProductMainImageCleanupService._new_item(
                    batch_id=batch.id,
                    product_id=product.id,
                    original_image_url="",
                    status=ProductMainImageCleanupStatus.SKIPPED.value,
                    skip_reason=ProductMainImageCleanupSkipReason.MISSING_MAIN_IMAGE.value,
                )
                session.add(item)
                items.append(item)
                continue

            existing = await ProductMainImageCleanupDAO.get_item_by_product_source(
                session,
                product_id=product.id,
                original_image_url=source_url,
            )
            if existing:
                skipped_existing.append(
                    {
                        "product_id": product.id,
                        "original_image_url": source_url,
                        "reason": ProductMainImageCleanupSkipReason.ALREADY_PROCESSED.value,
                        "existing_item_id": existing.id,
                        "existing_status": existing.status,
                    }
                )
                continue

            source_image = await ProductMainImageCleanupDAO.get_source_product_image(
                session,
                product_id=product.id,
                image_url=source_url,
            )
            item = ProductMainImageCleanupService._new_item(
                batch_id=batch.id,
                product_id=product.id,
                source_product_image_id=source_image.id if source_image else None,
                original_image_url=source_url,
                status=ProductMainImageCleanupStatus.PENDING.value,
                processor_method=active_processor.processor_method,
                processor_version=active_processor.processor_version,
            )
            session.add(item)
            await session.flush()

            source_path = ProductMainImageCleanupService._local_media_path_for_url(source_url)
            if source_path is None:
                ProductMainImageCleanupService._mark_skipped(
                    item,
                    ProductMainImageCleanupSkipReason.REMOTE_SOURCE_UNSUPPORTED.value,
                )
                items.append(item)
                continue
            if not source_path.exists():
                ProductMainImageCleanupService._mark_skipped(
                    item,
                    ProductMainImageCleanupSkipReason.MISSING_LOCAL_SOURCE.value,
                )
                items.append(item)
                continue
            if ProductMainImageCleanupService._source_is_already_transparent(source_path):
                ProductMainImageCleanupService._mark_skipped(
                    item,
                    ProductMainImageCleanupSkipReason.ALREADY_TRANSPARENT.value,
                )
                items.append(item)
                continue

            await ProductMainImageCleanupService._process_item(
                item,
                source_path=source_path,
                storage=active_storage,
                processor=active_processor,
            )
            items.append(item)

        batch.status = "completed"
        batch.updated_at = datetime.now()
        batch.completed_at = batch.updated_at
        session.add(batch)
        await session.commit()

        product_lookup = {int(product.id): product for product in products if product.id is not None}

        return {
            "batch": ProductMainImageCleanupService.serialize_batch(batch),
            "items": ProductMainImageCleanupService.serialize_items(
                items,
                product_lookup=product_lookup,
            ),
            "created_count": len(items),
            "candidate_ready_count": sum(
                1
                for item in items
                if item.status == ProductMainImageCleanupStatus.CANDIDATE_READY.value
            ),
            "skipped_count": sum(
                1
                for item in items
                if item.status == ProductMainImageCleanupStatus.SKIPPED.value
            ),
            "failed_count": sum(
                1 for item in items if item.status == ProductMainImageCleanupStatus.FAILED.value
            ),
            "already_processed_count": len(skipped_existing),
            "skipped_existing": skipped_existing[:100],
        }

    @staticmethod
    async def list_batches(
        session: AsyncSession,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        batches = await ProductMainImageCleanupDAO.list_batches(
            session,
            limit=safe_limit,
            offset=safe_offset,
        )
        return {"items": [ProductMainImageCleanupService.serialize_batch(item) for item in batches]}

    @staticmethod
    async def list_items(
        session: AsyncSession,
        *,
        batch_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        items = await ProductMainImageCleanupDAO.list_items(
            session,
            batch_id=batch_id,
            status=status,
            limit=safe_limit,
            offset=safe_offset,
        )
        product_lookup = await ProductMainImageCleanupService._product_lookup(session, items)
        return {
            "items": ProductMainImageCleanupService.serialize_items(
                items,
                product_lookup=product_lookup,
            )
        }

    @staticmethod
    async def approve_items(
        session: AsyncSession,
        *,
        item_ids: list[int],
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        unique_ids = ProductMainImageCleanupService._normalize_ids(item_ids)
        approved: list[ProductMainImageCleanupItem] = []
        updated_product_ids: list[int] = []
        updated_slugs: list[str] = []
        skipped: list[dict[str, Any]] = []
        now = datetime.now()

        for item_id in unique_ids:
            item = await session.get(ProductMainImageCleanupItem, item_id)
            if not item:
                skipped.append({"item_id": item_id, "reason": "not_found"})
                continue
            if item.status == ProductMainImageCleanupStatus.APPROVED.value:
                skipped.append({"item_id": item_id, "reason": "already_approved"})
                continue
            if (
                item.status != ProductMainImageCleanupStatus.CANDIDATE_READY.value
                or not item.candidate_image_url
            ):
                skipped.append({"item_id": item_id, "reason": "candidate_not_ready"})
                continue

            product = await session.get(Product, item.product_id)
            if not product:
                item.status = ProductMainImageCleanupStatus.FAILED.value
                item.failure_reason = "Product not found during approval"
                item.updated_at = now
                session.add(item)
                skipped.append({"item_id": item_id, "reason": "product_not_found"})
                continue

            if product.main_image != item.candidate_image_url:
                product.main_image = item.candidate_image_url
                if product.id is not None:
                    updated_product_ids.append(int(product.id))
                if product.slug:
                    updated_slugs.append(product.slug)
            item.status = ProductMainImageCleanupStatus.APPROVED.value
            item.approved_image_url = item.candidate_image_url
            item.approved_by = approved_by
            item.approved_at = now
            item.updated_at = now
            session.add(product)
            session.add(item)
            approved.append(item)

        if updated_product_ids:
            await CatalogRevisionService.bump_commit_and_purge(
                session,
                scope="product_main_image_cleanup_approval",
                product_ids=updated_product_ids,
                slugs=updated_slugs,
            )
        else:
            await session.commit()
        product_lookup = await ProductMainImageCleanupService._product_lookup(session, approved)
        return {
            "updated_count": len(approved),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "items": ProductMainImageCleanupService.serialize_items(
                approved,
                product_lookup=product_lookup,
            ),
        }

    @staticmethod
    async def reject_items(
        session: AsyncSession,
        *,
        item_ids: list[int],
        reason: str,
    ) -> dict[str, Any]:
        unique_ids = ProductMainImageCleanupService._normalize_ids(item_ids)
        rejected: list[ProductMainImageCleanupItem] = []
        skipped: list[dict[str, Any]] = []
        now = datetime.now()
        for item_id in unique_ids:
            item = await session.get(ProductMainImageCleanupItem, item_id)
            if not item:
                skipped.append({"item_id": item_id, "reason": "not_found"})
                continue
            if item.status == ProductMainImageCleanupStatus.APPROVED.value:
                skipped.append({"item_id": item_id, "reason": "already_approved"})
                continue
            item.status = ProductMainImageCleanupStatus.REJECTED.value
            item.reject_reason = reason
            item.updated_at = now
            session.add(item)
            rejected.append(item)
        await session.commit()
        product_lookup = await ProductMainImageCleanupService._product_lookup(session, rejected)
        return {
            "updated_count": len(rejected),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "items": ProductMainImageCleanupService.serialize_items(
                rejected,
                product_lookup=product_lookup,
            ),
        }

    @staticmethod
    async def skip_items(
        session: AsyncSession,
        *,
        item_ids: list[int],
        reason: str,
    ) -> dict[str, Any]:
        unique_ids = ProductMainImageCleanupService._normalize_ids(item_ids)
        skipped_items: list[ProductMainImageCleanupItem] = []
        skipped: list[dict[str, Any]] = []
        now = datetime.now()
        for item_id in unique_ids:
            item = await session.get(ProductMainImageCleanupItem, item_id)
            if not item:
                skipped.append({"item_id": item_id, "reason": "not_found"})
                continue
            if item.status == ProductMainImageCleanupStatus.APPROVED.value:
                skipped.append({"item_id": item_id, "reason": "already_approved"})
                continue
            ProductMainImageCleanupService._mark_skipped(item, reason, now=now)
            session.add(item)
            skipped_items.append(item)
        await session.commit()
        product_lookup = await ProductMainImageCleanupService._product_lookup(
            session,
            skipped_items,
        )
        return {
            "updated_count": len(skipped_items),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "items": ProductMainImageCleanupService.serialize_items(
                skipped_items,
                product_lookup=product_lookup,
            ),
        }

    @staticmethod
    def skip_reasons() -> dict[str, Any]:
        return {"items": [item.value for item in ProductMainImageCleanupSkipReason]}

    @staticmethod
    def serialize_batch(batch: ProductMainImageCleanupBatch) -> dict[str, Any]:
        return {
            "id": batch.id,
            "status": batch.status,
            "requested_limit": batch.requested_limit,
            "processor_method": batch.processor_method,
            "processor_version": batch.processor_version,
            "created_by": batch.created_by,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "completed_at": batch.completed_at,
        }

    @staticmethod
    def serialize_items(
        items: list[ProductMainImageCleanupItem],
        *,
        product_lookup: dict[int, Product] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            ProductMainImageCleanupService.serialize_item(
                item,
                product=product_lookup.get(item.product_id) if product_lookup else None,
            )
            for item in items
        ]

    @staticmethod
    def serialize_item(
        item: ProductMainImageCleanupItem,
        *,
        product: Product | None = None,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "batch_id": item.batch_id,
            "product_id": item.product_id,
            "product_title": product.title if product else None,
            "product_slug": product.slug if product else None,
            "product_brand_id": product.brand_id if product else None,
            "product_brand_title": product.brand.title if product and product.brand else None,
            "product_series_id": product.series_id if product else None,
            "product_series_title": product.series.title if product and product.series else None,
            "product_model": ProductMainImageCleanupService._product_model(product),
            "product_current_main_image": product.main_image if product else None,
            "source_product_image_id": item.source_product_image_id,
            "original_image_url": item.original_image_url,
            "candidate_image_url": item.candidate_image_url,
            "approved_image_url": item.approved_image_url,
            "status": item.status,
            "skip_reason": item.skip_reason,
            "reject_reason": item.reject_reason,
            "failure_reason": item.failure_reason,
            "processor_method": item.processor_method,
            "processor_version": item.processor_version,
            "confidence_score": item.confidence_score,
            "quality_score": item.quality_score,
            "candidate_storage_provider": item.candidate_storage_provider,
            "candidate_content_hash": item.candidate_content_hash,
            "candidate_width": item.candidate_width,
            "candidate_height": item.candidate_height,
            "approved_by": item.approved_by,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "approved_at": item.approved_at,
        }

    @staticmethod
    def _new_item(
        *,
        batch_id: int | None,
        product_id: int,
        original_image_url: str,
        status: str,
        source_product_image_id: int | None = None,
        skip_reason: str | None = None,
        processor_method: str | None = None,
        processor_version: str | None = None,
    ) -> ProductMainImageCleanupItem:
        now = datetime.now()
        return ProductMainImageCleanupItem(
            batch_id=batch_id,
            product_id=product_id,
            source_product_image_id=source_product_image_id,
            original_image_url=original_image_url,
            status=status,
            skip_reason=skip_reason,
            processor_method=processor_method,
            processor_version=processor_version,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    async def _process_item(
        item: ProductMainImageCleanupItem,
        *,
        source_path: Path,
        storage: ProductMediaStorage,
        processor: ProductMainImageCleanupProcessorAdapter,
    ) -> None:
        now = datetime.now()
        item.status = ProductMainImageCleanupStatus.PROCESSING.value
        item.updated_at = now
        try:
            processed = await processor.process(
                source_content=source_path.read_bytes(),
                context=ProductMainImageCleanupContext(
                    product_id=item.product_id,
                    source_url=item.original_image_url,
                    source_product_image_id=item.source_product_image_id,
                ),
            )
            stored = await storage.save_product_variant(
                content=processed.content,
                variant_type=MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
                extension=processed.extension,
            )
        except Exception as exc:
            item.status = ProductMainImageCleanupStatus.FAILED.value
            item.failure_reason = str(exc)
            item.updated_at = datetime.now()
            return

        item.status = ProductMainImageCleanupStatus.CANDIDATE_READY.value
        item.candidate_image_url = stored.url
        item.candidate_storage_provider = stored.storage_provider
        item.candidate_content_hash = stored.content_hash
        item.candidate_width = processed.width
        item.candidate_height = processed.height
        item.processor_method = processed.processor_method
        item.processor_version = processed.processor_version
        item.confidence_score = processed.confidence_score
        item.quality_score = processed.quality_score
        item.failure_reason = None
        item.updated_at = datetime.now()

    @staticmethod
    def _mark_skipped(
        item: ProductMainImageCleanupItem,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> None:
        item.status = ProductMainImageCleanupStatus.SKIPPED.value
        item.skip_reason = reason
        item.updated_at = now or datetime.now()

    @staticmethod
    async def _product_lookup(
        session: AsyncSession,
        items: list[ProductMainImageCleanupItem],
    ) -> dict[int, Product]:
        product_ids = [item.product_id for item in items]
        unique_ids = [int(product_id) for product_id in dict.fromkeys(product_ids)]
        return await ProductMainImageCleanupDAO.list_products_by_ids(session, unique_ids)

    @staticmethod
    def _product_model(product: Product | None) -> str | None:
        if not product:
            return None
        specs = product.specs or {}
        for key in ("model", "model_name", "модель", "Модель"):
            value = specs.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _local_media_path_for_url(url: str) -> Path | None:
        if not url:
            return None
        if url.startswith("/media/"):
            return Path(url.lstrip("/"))
        if url.startswith("media/"):
            return Path(url)
        return None

    @staticmethod
    def _source_is_already_transparent(source_path: Path) -> bool:
        try:
            with Image.open(source_path) as image:
                transposed = ImageOps.exif_transpose(image)
                has_alpha = transposed.mode in {"RGBA", "LA"} or (
                    transposed.mode == "P" and "transparency" in transposed.info
                )
                if not has_alpha:
                    return False

                rgba = transposed.convert("RGBA")
                alpha = rgba.getchannel("A")
                bbox = alpha.getbbox()
                if bbox is None:
                    return True

                full_area = rgba.width * rgba.height
                if full_area <= 0:
                    return False
                bbox_area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
                transparent_ratio = 1.0 - (bbox_area / full_area)
                return (
                    transparent_ratio >= 0.02
                    and ProductMainImageCleanupService._alpha_border_has_transparency(alpha)
                )
        except (OSError, UnidentifiedImageError, ValueError):
            return False

    @staticmethod
    def _alpha_border_has_transparency(alpha: Image.Image) -> bool:
        width, height = alpha.size
        if width <= 0 or height <= 0:
            return False

        edge_crops = [alpha.crop((0, 0, width, 1))]
        if height > 1:
            edge_crops.append(alpha.crop((0, height - 1, width, height)))
        if height > 2:
            edge_crops.append(alpha.crop((0, 1, 1, height - 1)))
            if width > 1:
                edge_crops.append(alpha.crop((width - 1, 1, width, height - 1)))
        return any(crop.getextrema()[0] < 250 for crop in edge_crops)

    @staticmethod
    def _normalize_ids(item_ids: list[int]) -> list[int]:
        unique_ids = [int(item_id) for item_id in dict.fromkeys(item_ids) if int(item_id) > 0]
        if not unique_ids:
            raise ValueError("item_ids is required")
        return unique_ids
