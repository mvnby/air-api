"""Prepare deterministic JPEG variants for the Yandex Business feed."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ProductImage, ProductImageVariant
from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.catalog_mutation_contracts import CatalogMutationBatch
from services.media_library_service import MediaLibraryService
from services.media_storage_service import ProductMediaStorage
from services.product_image_processing_contract import (
    ProductImageProcessingProvider,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_variant_service import ProductImageVariantService


@dataclass(frozen=True)
class YandexFeedImageSource:
    url: str
    content_hash: str | None


class YandexFeedImageService:
    VARIANT_TYPE = ProductImageVariantType.YANDEX_FEED.value
    WIDTH = 800
    HEIGHT = 800

    @classmethod
    async def backfill(
        cls,
        session: AsyncSession,
        *,
        execute: bool,
        limit: int = 100,
        product_id: int | None = None,
        after_product_id: int | None = None,
        force: bool = False,
        storage: ProductMediaStorage | None = None,
    ) -> dict[str, Any]:
        products = await cls._load_products(
            session,
            limit=limit,
            product_id=product_id,
            after_product_id=after_product_id,
        )
        plan = cls._build_plan(products, force=force)
        result = {
            "dry_run": not execute,
            "limit": max(1, min(int(limit), 1000)),
            "product_id": product_id,
            "after_product_id": after_product_id,
            "next_after_product_id": int(products[-1].id) if products else after_product_id,
            "inspected": len(products),
            "planned": len(plan["planned"]),
            "up_to_date": len(plan["up_to_date"]),
            "missing_sources": plan["missing_sources"],
            "items": plan["planned"],
            "processed": 0,
            "errors": [],
        }
        if not execute:
            return result

        processed: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        mutation_batch = CatalogMutationBatch()
        products_by_id = {int(product.id): product for product in products}
        for item in plan["planned"]:
            product = products_by_id[item["product_id"]]
            try:
                item_batch = CatalogMutationBatch()
                async with session.begin_nested():
                    image = cls._main_product_image(product)
                    if image is None:
                        image = ProductImage(
                            product_id=int(product.id),
                            url=str(product.main_image),
                            is_installation_photo=False,
                        )
                        session.add(image)
                        await session.flush()
                        item_batch.record(
                            changed=True,
                            product_ids=[product.id],
                        )
                    source_url = item["source_url"]
                    source_content: bytes | None = None
                    if cls._is_external_source(source_url):
                        source_url, source_content = await cls._ingest_external_original(
                            session,
                            image=image,
                            source_url=source_url,
                            storage=storage,
                        )
                    variant = await ProductImageVariantService.reprocess_variant(
                        session,
                        product_image_id=int(image.id),
                        variant_type=cls.VARIANT_TYPE,
                        provider=ProductImageProcessingProvider.NOOP.value,
                        storage=storage,
                        source_url_override=source_url,
                        source_content_override=source_content,
                        force=force,
                        commit=False,
                        mutation_batch=item_batch,
                    )
                mutation_batch.record(
                    changed=item_batch.changed,
                    product_ids=item_batch.product_ids,
                )
                if variant["processing_status"] != ProductImageProcessingStatus.READY.value:
                    errors.append(
                        {
                            "product_id": int(product.id),
                            "product_title": product.title,
                            "product_image_id": int(image.id),
                            "error": variant.get("processing_error") or "variant_not_ready",
                        }
                    )
                    continue
                processed.append(
                    {
                        "product_id": int(product.id),
                        "product_title": product.title,
                        "product_image_id": int(image.id),
                        "variant_id": variant["id"],
                        "url": variant["url"],
                        "content_hash": variant["content_hash"],
                        "source_content_hash": variant["source_content_hash"],
                        "width": variant["width"],
                        "height": variant["height"],
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "product_id": int(product.id),
                        "product_title": product.title,
                        "error": str(exc),
                    }
                )

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="yandex_feed_image.backfill",
            changed=mutation_batch.changed,
            product_ids=sorted(mutation_batch.product_ids),
        )
        return {
            **result,
            "processed": len(processed),
            "processed_items": processed,
            "errors": errors,
        }

    @classmethod
    async def _load_products(
        cls,
        session: AsyncSession,
        *,
        limit: int,
        product_id: int | None,
        after_product_id: int | None,
    ) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.is_published.is_(True), Product.price > 0)
            .options(
                selectinload(Product.gallery_images).selectinload(ProductImage.variants)
            )
            .order_by(Product.id.asc())
            .limit(max(1, min(int(limit), 1000)))
            .execution_options(populate_existing=True)
        )
        if product_id is not None:
            stmt = stmt.where(Product.id == product_id)
        if after_product_id is not None:
            stmt = stmt.where(Product.id > after_product_id)
        result = await session.execute(stmt)
        return list(result.scalars().unique().all())

    @classmethod
    def _build_plan(
        cls,
        products: list[Product],
        *,
        force: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        planned: list[dict[str, Any]] = []
        up_to_date: list[dict[str, Any]] = []
        missing_sources: list[dict[str, Any]] = []
        for product in products:
            main_image = str(product.main_image or "").strip()
            if not main_image:
                missing_sources.append(
                    {
                        "product_id": int(product.id),
                        "product_title": product.title,
                        "reason": "missing_main_image",
                    }
                )
                continue

            image = cls._main_product_image(product)
            source = cls._source_for_image(image, fallback_url=main_image)
            variant = cls._variant_for_image(image)
            item = {
                "product_id": int(product.id),
                "product_title": product.title,
                "product_image_id": int(image.id) if image and image.id else None,
                "will_create_product_image": image is None,
                "source_url": source.url,
                "source_content_hash": source.content_hash,
                "current_variant_url": variant.url if variant else None,
            }
            if not force and cls._is_current(variant, source):
                up_to_date.append({**item, "reason": "up_to_date"})
                continue

            reason = "missing_variant"
            if variant:
                if variant.processing_status == ProductImageProcessingStatus.FAILED.value:
                    reason = "failed_variant"
                elif variant.source_url != source.url:
                    reason = "stale_source"
                else:
                    reason = "invalid_variant"
            planned.append({**item, "reason": "forced" if force else reason})
        return {
            "planned": planned,
            "up_to_date": up_to_date,
            "missing_sources": missing_sources,
        }

    @staticmethod
    def _same_url(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False
        return left == right or left.strip("/") == right.strip("/")

    @classmethod
    def _main_product_image(cls, product: Product) -> ProductImage | None:
        return next(
            (
                image
                for image in (product.gallery_images or [])
                if not image.is_installation_photo
                and cls._same_url(image.url, product.main_image)
            ),
            None,
        )

    @staticmethod
    def _is_external_source(url: str) -> bool:
        normalized = str(url or "").strip()
        return normalized.startswith(("http://", "https://")) and not (
            ProductImageVariantService._is_configured_remote_media_url(normalized)
        )

    @classmethod
    async def _ingest_external_original(
        cls,
        session: AsyncSession,
        *,
        image: ProductImage,
        source_url: str,
        storage: ProductMediaStorage | None,
    ) -> tuple[str, bytes]:
        content, _ = await MediaLibraryService.download_remote_image(source_url)
        extension, width, height = cls._source_image_metadata(content)
        original = await ProductImageVariantService.ensure_original_variant(
            session,
            image,
            storage=storage,
            source_content=content,
            extension=extension,
            width=width,
            height=height,
        )
        await session.flush()
        return str(original.url), content

    @staticmethod
    def _source_image_metadata(content: bytes) -> tuple[str, int, int]:
        with Image.open(BytesIO(content)) as image:
            image_format = str(image.format or "").strip().lower()
            extension = {
                "jpeg": "jpg",
                "png": "png",
                "webp": "webp",
            }.get(image_format)
            if extension is None:
                raise ValueError("Remote source image format is not supported")
            return extension, image.width, image.height

    @classmethod
    def _source_for_image(
        cls,
        image: ProductImage | None,
        *,
        fallback_url: str,
    ) -> YandexFeedImageSource:
        if image is not None:
            originals = sorted(
                (
                    variant
                    for variant in (image.variants or [])
                    if variant.variant_type == ProductImageVariantType.ORIGINAL.value
                    and variant.processing_status
                    == ProductImageProcessingStatus.READY.value
                    and variant.url
                ),
                key=lambda variant: int(variant.id or 0),
            )
            if originals:
                original = originals[0]
                return YandexFeedImageSource(
                    url=str(original.url),
                    content_hash=original.content_hash,
                )
        return YandexFeedImageSource(url=fallback_url, content_hash=None)

    @classmethod
    def _variant_for_image(
        cls,
        image: ProductImage | None,
    ) -> ProductImageVariant | None:
        if image is None:
            return None
        return next(
            (
                variant
                for variant in (image.variants or [])
                if variant.variant_type == cls.VARIANT_TYPE
            ),
            None,
        )

    @classmethod
    def _is_current(
        cls,
        variant: ProductImageVariant | None,
        source: YandexFeedImageSource,
    ) -> bool:
        if (
            variant is None
            or variant.processing_status != ProductImageProcessingStatus.READY.value
            or not variant.url
            or variant.source_url != source.url
            or variant.width != cls.WIDTH
            or variant.height != cls.HEIGHT
        ):
            return False
        if source.content_hash and variant.source_content_hash != source.content_hash:
            return False
        path = urlsplit(variant.url).path.lower()
        return path.endswith((".jpg", ".jpeg", ".png"))
