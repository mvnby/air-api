"""Service methods for product image variants and processing state."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from PIL import Image
from sqlalchemy import exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import ProductImage, ProductImageVariant
from services.media_storage_service import ProductMediaStorage, get_product_media_storage
from services.product_image_processing_contract import (
    CATALOG_VARIANT_TYPES,
    ProductImageManualQualityStatus,
    ProductImageProcessingProvider,
    ProductImageProcessingStage,
    ProductImageProcessingStatus,
    ProductImageVariantType,
    normalize_processing_provider,
    normalize_variant_type,
)
from services.product_image_processing_provider import (
    ProductImageProcessingContext,
    ProductImageProcessor,
    get_product_image_processor,
)


MAX_SOURCE_IMAGE_BYTES = 20 * 1024 * 1024
SOURCE_IMAGE_TIMEOUT_SECONDS = 12.0


class ProductImageVariantService:
    @staticmethod
    async def ensure_original_variant(
        session: AsyncSession,
        image: ProductImage,
        *,
        storage_provider: str = "local",
        storage: ProductMediaStorage | None = None,
        source_content: bytes | None = None,
        extension: str = "webp",
        width: int | None = None,
        height: int | None = None,
    ) -> ProductImageVariant:
        """Create a ready `original` variant without changing ProductImage.url."""
        if image.id is None:
            await session.flush()

        variant = await ProductImageVariantService._get_or_create_variant(
            session,
            product_image_id=image.id,
            variant_type=ProductImageVariantType.ORIGINAL.value,
        )
        now = datetime.now()
        if source_content is not None:
            active_storage = storage or get_product_media_storage()
            stored = await active_storage.save_product_variant(
                content=source_content,
                variant_type=ProductImageVariantType.ORIGINAL.value,
                extension=extension,
            )
            variant.url = stored.url
            variant.storage_provider = stored.storage_provider
            variant.content_hash = stored.content_hash
            if width is None or height is None:
                detected_width, detected_height = ProductImageVariantService._image_size(
                    source_content
                )
                width = width or detected_width
                height = height or detected_height
            variant.width = width
            variant.height = height
        elif not variant.url:
            variant.url = image.url
            variant.storage_provider = storage_provider
        variant.processing_status = ProductImageProcessingStatus.READY.value
        variant.processing_stage = ProductImageProcessingStage.ORIGINAL_INGEST.value
        variant.processing_provider = ProductImageProcessingProvider.MANUAL.value
        variant.manual_quality_status = ProductImageManualQualityStatus.UNREVIEWED.value
        variant.processing_error = None
        variant.processed_at = variant.processed_at or now
        variant.updated_at = now
        session.add(variant)
        return variant

    @staticmethod
    async def get_missing_variant_candidates(
        session: AsyncSession,
        *,
        variant_type: str = ProductImageVariantType.CARD.value,
        limit: int = 100,
        include_installation: bool = False,
        product_id: int | None = None,
        only_missing: bool = True,
        retry_failed: bool = False,
    ) -> dict[str, Any]:
        """Return dry-run candidates whose requested variant is absent or failed."""
        normalized_type = normalize_variant_type(variant_type).value
        safe_limit = max(1, min(int(limit), 100))

        any_variant_exists = exists(
            select(ProductImageVariant.id).where(
                ProductImageVariant.product_image_id == ProductImage.id,
                ProductImageVariant.variant_type == normalized_type,
            )
        )
        failed_variant_exists = exists(
            select(ProductImageVariant.id).where(
                ProductImageVariant.product_image_id == ProductImage.id,
                ProductImageVariant.variant_type == normalized_type,
                ProductImageVariant.processing_status == ProductImageProcessingStatus.FAILED.value,
            )
        )

        candidate_conditions = []
        if only_missing or not retry_failed:
            candidate_conditions.append(~any_variant_exists)
        if retry_failed:
            candidate_conditions.append(failed_variant_exists)

        candidate_filter = or_(*candidate_conditions)
        count_stmt = select(func.count()).select_from(ProductImage).where(candidate_filter)
        stmt = select(ProductImage).where(candidate_filter)

        if product_id is not None:
            count_stmt = count_stmt.where(ProductImage.product_id == product_id)
            stmt = stmt.where(ProductImage.product_id == product_id)

        if not include_installation:
            count_stmt = count_stmt.where(ProductImage.is_installation_photo == False)  # noqa: E712
            stmt = stmt.where(ProductImage.is_installation_photo == False)  # noqa: E712

        failed_variant_ids_stmt = select(ProductImageVariant.product_image_id).where(
            ProductImageVariant.variant_type == normalized_type,
            ProductImageVariant.processing_status == ProductImageProcessingStatus.FAILED.value,
        )
        if product_id is not None:
            failed_variant_ids_stmt = failed_variant_ids_stmt.join(ProductImage).where(
                ProductImage.product_id == product_id
            )

        failed_variant_ids = set((await session.execute(failed_variant_ids_stmt)).scalars().all())
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        rows = (await session.execute(stmt.order_by(ProductImage.id).limit(safe_limit))).scalars().all()

        candidates = [
            {
                "product_image_id": image.id,
                "product_id": image.product_id,
                "url": image.url,
                "is_installation_photo": image.is_installation_photo,
                "reason": "failed_variant" if image.id in failed_variant_ids else "missing_variant",
            }
            for image in rows
        ]
        return {
            "dry_run": True,
            "variant_type": normalized_type,
            "total_candidates": total,
            "returned": len(candidates),
            "candidates": candidates,
        }

    @staticmethod
    async def process_missing_variants(
        session: AsyncSession,
        *,
        variant_type: str = ProductImageVariantType.CARD.value,
        limit: int = 100,
        include_installation: bool = False,
        dry_run: bool = True,
        provider: str = ProductImageProcessingProvider.NOOP.value,
        storage: ProductMediaStorage | None = None,
        processor: ProductImageProcessor | None = None,
        rembg_model: str | None = None,
        product_id: int | None = None,
        only_missing: bool = True,
        retry_failed: bool = False,
    ) -> dict[str, Any]:
        candidates = await ProductImageVariantService.get_missing_variant_candidates(
            session,
            variant_type=variant_type,
            limit=limit,
            include_installation=include_installation,
            product_id=product_id,
            only_missing=only_missing,
            retry_failed=retry_failed,
        )
        if dry_run:
            return candidates

        processed: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        variants: list[dict[str, Any]] = []
        for item in candidates["candidates"]:
            image_id = item["product_image_id"]
            try:
                result = await ProductImageVariantService.reprocess_variant(
                    session,
                    product_image_id=image_id,
                    variant_type=variant_type,
                    provider=provider,
                    storage=storage,
                    processor=processor,
                    rembg_model=rembg_model,
                    commit=False,
                )
                variants.append(result)
                if result.get("processing_status") == ProductImageProcessingStatus.READY.value:
                    processed.append(result)
                elif result.get("processing_status") == ProductImageProcessingStatus.FAILED.value:
                    errors.append(
                        {
                            "product_image_id": image_id,
                            "status": result.get("processing_status"),
                            "error": result.get("processing_error"),
                        }
                    )
            except Exception as exc:
                await ProductImageVariantService._record_processing_error(
                    session,
                    product_image_id=image_id,
                    variant_type=variant_type,
                    provider=provider,
                    status=ProductImageProcessingStatus.FAILED.value,
                    stage=ProductImageProcessingStage.VARIANT_GENERATION.value,
                    error=str(exc),
                )
                errors.append({"product_image_id": image_id, "error": str(exc)})

        await session.commit()
        return {
            "dry_run": False,
            "variant_type": normalize_variant_type(variant_type).value,
            "total_candidates": candidates["total_candidates"],
            "returned": candidates["returned"],
            "candidates": candidates["candidates"],
            "processed": len(processed),
            "errors": errors,
            "variants": variants,
        }

    @staticmethod
    async def reprocess_variant(
        session: AsyncSession,
        *,
        product_image_id: int,
        variant_type: str = ProductImageVariantType.CARD.value,
        provider: str = ProductImageProcessingProvider.NOOP.value,
        storage: ProductMediaStorage | None = None,
        processor: ProductImageProcessor | None = None,
        rembg_model: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_type = normalize_variant_type(variant_type).value
        normalized_provider = normalize_processing_provider(provider).value
        image = await session.get(ProductImage, product_image_id)
        if not image:
            raise LookupError("ProductImage not found")

        variant = await ProductImageVariantService._get_or_create_variant(
            session,
            product_image_id=product_image_id,
            variant_type=normalized_type,
        )
        active_processor = processor or get_product_image_processor(
            normalized_provider,
            rembg_model=rembg_model,
        )
        effective_provider = getattr(active_processor, "provider_name", normalized_provider)
        now = datetime.now()
        variant.processing_status = ProductImageProcessingStatus.PROCESSING.value
        variant.processing_stage = ProductImageProcessingStage.VARIANT_GENERATION.value
        variant.processing_provider = effective_provider
        variant.processing_error = None
        variant.updated_at = now
        session.add(variant)
        await session.flush()

        if image.is_installation_photo and normalized_type in CATALOG_VARIANT_TYPES:
            variant.processing_status = ProductImageProcessingStatus.SKIPPED.value
            variant.processing_stage = ProductImageProcessingStage.QUALITY_MANUAL_APPROVAL.value
            variant.processing_error = "Installation photos are excluded from catalog variants"
            variant.updated_at = datetime.now()
            session.add(variant)
            if commit:
                await session.commit()
            return ProductImageVariantService.serialize_variant(variant)

        try:
            source_content = await ProductImageVariantService._source_content_for_url(image.url)
        except Exception as exc:
            variant.processing_status = ProductImageProcessingStatus.FAILED.value
            variant.processing_stage = ProductImageProcessingStage.ORIGINAL_INGEST.value
            variant.processing_error = str(exc)
            variant.updated_at = datetime.now()
            session.add(variant)
            if commit:
                await session.commit()
            return ProductImageVariantService.serialize_variant(variant)

        if source_content is None:
            variant.processing_status = ProductImageProcessingStatus.FAILED.value
            variant.processing_stage = ProductImageProcessingStage.ORIGINAL_INGEST.value
            variant.processing_error = "Source image is not available in local media storage"
            variant.updated_at = datetime.now()
            session.add(variant)
            if commit:
                await session.commit()
            return ProductImageVariantService.serialize_variant(variant)

        active_storage = storage or get_product_media_storage()
        try:
            processed = await active_processor.process(
                source_content=source_content,
                context=ProductImageProcessingContext(
                    product_image_id=product_image_id,
                    source_url=image.url,
                    variant_type=normalized_type,
                ),
            )
            stored = await active_storage.save_product_variant(
                content=processed.content,
                variant_type=normalized_type,
                extension=processed.extension,
            )
            width, height = ProductImageVariantService._image_size(processed.content)
        except Exception as exc:
            variant.processing_status = ProductImageProcessingStatus.FAILED.value
            variant.processing_stage = ProductImageProcessingStage.VARIANT_GENERATION.value
            variant.processing_error = str(exc)
            variant.updated_at = datetime.now()
            session.add(variant)
            if commit:
                await session.commit()
            return ProductImageVariantService.serialize_variant(variant)

        variant.url = stored.url
        variant.storage_provider = stored.storage_provider
        variant.content_hash = stored.content_hash
        variant.width = processed.width or width
        variant.height = processed.height or height
        variant.processing_status = ProductImageProcessingStatus.READY.value
        variant.processing_stage = ProductImageProcessingStage.STORAGE_SAVE.value
        variant.manual_quality_status = ProductImageManualQualityStatus.UNREVIEWED.value
        variant.processing_error = None
        variant.processed_at = datetime.now()
        variant.updated_at = variant.processed_at
        session.add(variant)
        if commit:
            await session.commit()
        return ProductImageVariantService.serialize_variant(variant)

    @staticmethod
    def serialize_variant(variant: ProductImageVariant) -> dict[str, Any]:
        return {
            "id": variant.id,
            "product_image_id": variant.product_image_id,
            "variant_type": variant.variant_type,
            "url": variant.url,
            "storage_provider": variant.storage_provider,
            "processing_status": variant.processing_status,
            "processing_stage": variant.processing_stage,
            "processing_provider": variant.processing_provider,
            "manual_quality_status": variant.manual_quality_status,
            "content_hash": variant.content_hash,
            "width": variant.width,
            "height": variant.height,
            "processing_error": variant.processing_error,
            "processed_at": variant.processed_at,
        }

    @staticmethod
    async def _get_or_create_variant(
        session: AsyncSession,
        *,
        product_image_id: int,
        variant_type: str,
    ) -> ProductImageVariant:
        existing = (
            await session.execute(
                select(ProductImageVariant).where(
                    ProductImageVariant.product_image_id == product_image_id,
                    ProductImageVariant.variant_type == variant_type,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        variant = ProductImageVariant(
            product_image_id=product_image_id,
            variant_type=variant_type,
            processing_status=ProductImageProcessingStatus.PENDING.value,
            processing_stage=ProductImageProcessingStage.ORIGINAL_INGEST.value,
        )
        session.add(variant)
        await session.flush()
        return variant

    @staticmethod
    async def _record_processing_error(
        session: AsyncSession,
        *,
        product_image_id: int,
        variant_type: str,
        provider: str,
        status: str,
        stage: str,
        error: str,
    ) -> None:
        variant = await ProductImageVariantService._get_or_create_variant(
            session,
            product_image_id=product_image_id,
            variant_type=normalize_variant_type(variant_type).value,
        )
        variant.processing_status = status
        variant.processing_stage = stage
        variant.processing_provider = normalize_processing_provider(provider).value
        variant.processing_error = error
        variant.updated_at = datetime.now()
        session.add(variant)

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
    async def _source_content_for_url(url: str) -> bytes | None:
        source_path = ProductImageVariantService._local_media_path_for_url(url)
        if source_path and source_path.exists():
            return source_path.read_bytes()
        if ProductImageVariantService._is_configured_remote_media_url(url):
            return await ProductImageVariantService._download_remote_media_content(url)
        return None

    @staticmethod
    def _is_configured_remote_media_url(url: str) -> bool:
        normalized = str(url or "").strip()
        if not normalized.startswith(("http://", "https://")):
            return False
        load_dotenv()
        prefixes = [
            os.getenv("PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", ""),
            os.getenv("MEDIA_S3_PUBLIC_BASE_URL", ""),
        ]
        for prefix in prefixes:
            clean_prefix = str(prefix or "").strip().rstrip("/")
            if clean_prefix and normalized.startswith(f"{clean_prefix}/"):
                return True
        return False

    @staticmethod
    async def _download_remote_media_content(url: str) -> bytes:
        async with httpx.AsyncClient(timeout=SOURCE_IMAGE_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "image/*"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                raise ValueError("Remote source is not an image")
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_SOURCE_IMAGE_BYTES:
                raise ValueError("Remote source image is too large")
            content = response.content
            if not content:
                raise ValueError("Remote source image is empty")
            if len(content) > MAX_SOURCE_IMAGE_BYTES:
                raise ValueError("Remote source image is too large")
            return content

    @staticmethod
    def _image_size(content: bytes) -> tuple[int | None, int | None]:
        try:
            from io import BytesIO

            with Image.open(BytesIO(content)) as img:
                return img.width, img.height
        except Exception:
            return None, None
