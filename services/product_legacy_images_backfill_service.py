"""Backfill legacy product image lists into canonical image variants."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Product, ProductImage, ProductImageVariant
from services.media_storage_service import ProductMediaStorage
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingProvider,
    ProductImageProcessingStage,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_variant_service import ProductImageVariantService
from services.product_serialization import parse_legacy_images


class ProductLegacyImagesBackfillService:
    @staticmethod
    async def backfill_to_storage(
        session: AsyncSession,
        *,
        storage: ProductMediaStorage,
        execute: bool,
        limit: int = 50,
        product_id: int | None = None,
        after_product_id: int | None = None,
        published_only: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 1000))
        plan = await ProductLegacyImagesBackfillService.build_backfill_plan(
            session,
            storage=storage,
            limit=safe_limit,
            product_id=product_id,
            after_product_id=after_product_id,
            published_only=published_only,
            force=force,
        )
        plan["dry_run"] = not execute
        if not execute:
            return plan

        uploaded: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        now = datetime.now()

        for item in plan["items"]:
            try:
                source_path = Path(item["source_path"])
                content = source_path.read_bytes()
                image = await ProductLegacyImagesBackfillService._resolve_product_image(
                    session,
                    product_id=item["product_id"],
                    image_id=item.get("product_image_id"),
                    url=item["image_url"],
                )
                stored = await storage.save_product_variant(
                    content=content,
                    variant_type=ProductImageVariantType.ORIGINAL.value,
                    extension=item["extension"],
                )
                variant = await ProductImageVariantService._get_or_create_variant(
                    session,
                    product_image_id=image.id,
                    variant_type=ProductImageVariantType.ORIGINAL.value,
                )
                width, height = ProductImageVariantService._image_size(content)
                variant.url = stored.url
                variant.storage_provider = stored.storage_provider
                variant.content_hash = stored.content_hash
                variant.width = variant.width or width
                variant.height = variant.height or height
                variant.processing_status = ProductImageProcessingStatus.READY.value
                variant.processing_stage = ProductImageProcessingStage.ORIGINAL_INGEST.value
                variant.processing_provider = ProductImageProcessingProvider.MANUAL.value
                variant.manual_quality_status = ProductImageManualQualityStatus.UNREVIEWED.value
                variant.processing_error = None
                variant.processed_at = variant.processed_at or now
                variant.updated_at = now
                session.add(variant)
                uploaded.append(
                    {
                        **item,
                        "product_image_id": image.id,
                        "target_url": stored.url,
                        "target_path": stored.path,
                        "storage_provider": stored.storage_provider,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "product_id": item["product_id"],
                        "image_url": item["image_url"],
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
    async def build_backfill_plan(
        session: AsyncSession,
        *,
        storage: ProductMediaStorage,
        limit: int,
        product_id: int | None,
        after_product_id: int | None,
        published_only: bool,
        force: bool,
    ) -> dict[str, Any]:
        stmt = select(Product).order_by(Product.id).limit(max(1, min(int(limit), 1000)))
        if published_only:
            stmt = stmt.where(Product.is_published.is_(True))
        if product_id is not None:
            stmt = stmt.where(Product.id == product_id)
        if after_product_id is not None:
            stmt = stmt.where(Product.id > after_product_id)

        products = (await session.execute(stmt)).scalars().all()
        items: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        inspected_images = 0
        for product in products:
            for image_url in ProductLegacyImagesBackfillService._legacy_image_urls(product):
                inspected_images += 1
                item = await ProductLegacyImagesBackfillService._plan_image(
                    session,
                    storage=storage,
                    product=product,
                    image_url=image_url,
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
            "after_product_id": after_product_id,
            "published_only": published_only,
            "force": force,
            "inspected": len(products),
            "inspected_images": inspected_images,
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
    def _legacy_image_urls(product: Product) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for url in parse_legacy_images(product.images):
            if not isinstance(url, str):
                continue
            normalized = url.strip()
            if not normalized:
                continue
            dedupe_key = normalized.strip("/")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            urls.append(normalized)
        return urls

    @staticmethod
    async def _plan_image(
        session: AsyncSession,
        *,
        storage: ProductMediaStorage,
        product: Product,
        image_url: str,
        force: bool,
    ) -> dict[str, Any]:
        base = {
            "planned": False,
            "product_id": product.id,
            "image_url": image_url,
            "product_image_id": None,
            "variant_id": None,
            "current_storage_provider": None,
            "current_variant_url": None,
        }
        source_path = ProductImageVariantService._local_media_path_for_url(image_url)
        if source_path is None:
            return {**base, "skip_reason": "non_local_url"}
        if not source_path.exists():
            return {
                **base,
                "source_path": str(source_path),
                "skip_reason": "missing_local_file",
            }

        image = await ProductLegacyImagesBackfillService._find_product_image(
            session,
            product_id=product.id,
            url=image_url,
        )
        variant = None
        if image:
            variant = (
                await session.execute(
                    select(ProductImageVariant).where(
                        ProductImageVariant.product_image_id == image.id,
                        ProductImageVariant.variant_type
                        == ProductImageVariantType.ORIGINAL.value,
                    )
                )
            ).scalar_one_or_none()
            if (
                variant
                and not force
                and variant.storage_provider == storage.provider_name
                and variant.url
                and variant.processing_status == ProductImageProcessingStatus.READY.value
            ):
                return {
                    **base,
                    "product_image_id": image.id,
                    "variant_id": variant.id,
                    "current_storage_provider": variant.storage_provider,
                    "current_variant_url": variant.url,
                    "skip_reason": "already_on_target_provider",
                }

        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        extension = source_path.suffix.lower().lstrip(".") or "webp"
        target = storage.build_product_variant_object(
            content_hash=content_hash,
            variant_type=ProductImageVariantType.ORIGINAL.value,
            extension=extension,
        )
        return {
            **base,
            "planned": True,
            "product_image_id": image.id if image else None,
            "variant_id": variant.id if variant else None,
            "current_storage_provider": variant.storage_provider if variant else None,
            "current_variant_url": variant.url if variant else None,
            "will_create_product_image": image is None,
            "source_path": str(source_path),
            "extension": extension,
            "content_hash": content_hash,
            "target_url": target.url,
            "target_path": target.path,
            "target_storage_provider": target.storage_provider,
        }

    @staticmethod
    async def _find_product_image(
        session: AsyncSession,
        *,
        product_id: int,
        url: str,
    ) -> ProductImage | None:
        normalized = url.strip("/")
        candidates = [url, normalized, f"/{normalized}"]
        return (
            await session.execute(
                select(ProductImage).where(
                    ProductImage.product_id == product_id,
                    ProductImage.url.in_(list(dict.fromkeys(candidates))),
                )
            )
        ).scalars().first()

    @staticmethod
    async def _resolve_product_image(
        session: AsyncSession,
        *,
        product_id: int,
        image_id: int | None,
        url: str,
    ) -> ProductImage:
        if image_id:
            image = await session.get(ProductImage, image_id)
            if image:
                return image
        image = ProductImage(product_id=product_id, url=url)
        session.add(image)
        await session.flush()
        return image
