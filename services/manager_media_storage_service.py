"""Storage, linking, search, and cleanup operations for manager product media."""

from __future__ import annotations

import asyncio
import os
from io import BytesIO
from pathlib import Path
from typing import List

import httpx
from duckduckgo_search import DDGS
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.logger import logger
from models import Product, ProductImage, ProductImageVariant
from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.product_image_processing_contract import (
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_variant_service import ProductImageVariantService
from services.product_original_media_service import ProductOriginalMediaService


class ManagerMediaStorageOperations:
    """Reusable storage domain mixed into the public manager-media facade."""

    @staticmethod
    async def search_reuse_products(
        session: AsyncSession,
        query: str,
        limit: int = 10,
    ) -> List[dict]:
        statement = select(Product).where(Product.title.ilike(f"%{query}%")).limit(limit)
        result = await session.execute(statement)
        products = result.scalars().all()
        return [
            {"id": product.id, "title": product.title, "main_image": product.main_image}
            for product in products
        ]

    @classmethod
    async def reuse_image_link(
        cls,
        session: AsyncSession,
        product_id: int,
        source_image_url: str,
    ) -> dict:
        product = await session.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")

        existing = (
            await session.execute(
                select(ProductImage).where(
                    ProductImage.product_id == product_id,
                    ProductImage.url == source_image_url,
                )
            )
        ).scalar_one_or_none()
        if existing:
            original_variant = (
                await session.execute(
                    select(ProductImageVariant).where(
                        ProductImageVariant.product_image_id == existing.id,
                        ProductImageVariant.variant_type
                        == ProductImageVariantType.ORIGINAL.value,
                    )
                )
            ).scalar_one_or_none()
            changed = (
                original_variant is None
                or not original_variant.url
                or original_variant.processing_status
                != ProductImageProcessingStatus.READY.value
            )
            if changed:
                await ProductImageVariantService.ensure_original_variant(session, existing)
            await CatalogInvalidationCommitService.commit_registered_global_mutation(
                session,
                producer="manager_media.reuse_image_link",
                changed=changed,
                product_ids=[product_id],
            )
            return {"message": "Image already linked", "id": existing.id}

        new_image = ProductImage(
            product_id=product_id,
            url=source_image_url,
            is_installation_photo=False,
        )
        session.add(new_image)
        await session.flush()
        await ProductImageVariantService.ensure_original_variant(session, new_image)
        await cls._sync_legacy_images(session, product_id)
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.reuse_image_link",
            changed=True,
            product_ids=[product_id],
        )
        return {"message": "Image linked", "id": new_image.id}

    @staticmethod
    async def search_images(query: str, max_results: int = 20) -> List[dict]:
        """Search images and degrade to an empty result on provider failures."""

        try:
            results = await asyncio.to_thread(
                lambda: list(DDGS().images(query, max_results=max_results))
            )
        except Exception as exc:
            if "Ratelimit" in str(exc) or "403" in str(exc):
                logger.warning("DDG Ratelimit hit for query: %s", query)
            else:
                logger.warning("Image search provider error (DDG): %s", exc)
            return []

        return [
            {
                "image": result.get("image"),
                "width": result.get("width"),
                "height": result.get("height"),
                "thumbnail": result.get("thumbnail"),
            }
            for result in results
            if result.get("image")
        ]

    @classmethod
    async def process_and_save_image(
        cls,
        url: str,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Download an image and attach it through the atomic upload boundary."""

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                image_content = response.content
        except Exception as exc:
            logger.warning("Failed to download external image: %s", exc)
            raise ValueError(f"Failed to download image: {exc}") from exc

        return await cls.save_image_from_bytes(
            image_content=image_content,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )

    @classmethod
    async def save_image_from_bytes(
        cls,
        image_content: bytes,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Attach one upload and commit its catalog invalidation atomically."""

        result, changed = await cls._stage_image_from_bytes(
            image_content=image_content,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.save_image_from_bytes",
            changed=changed,
            product_ids=[product_id],
        )
        return result

    @classmethod
    async def save_images_from_bytes(
        cls,
        file_payloads: List[bytes],
        product_id: int,
        session: AsyncSession,
        *,
        set_main_if_missing: bool,
        is_installation: bool = False,
    ) -> List[dict]:
        """Attach a local upload batch in one catalog transaction."""

        product = await session.get(Product, product_id)
        if not product:
            raise LookupError("Product not found")

        uploaded_images: List[dict] = []
        changed = False
        for image_content in file_payloads:
            should_set_main = bool(
                set_main_if_missing
                and not product.main_image
                and not is_installation
                and not uploaded_images
            )
            try:
                async with session.begin_nested():
                    result, image_changed = await cls._stage_image_from_bytes(
                        image_content=image_content,
                        product_id=product_id,
                        session=session,
                        set_main=should_set_main,
                        is_installation=is_installation,
                    )
            except ValueError as exc:
                logger.error("Failed to upload local image: %s", exc)
                continue
            uploaded_images.append(result)
            changed = changed or image_changed

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.save_images_from_bytes",
            changed=changed,
            product_ids=[product_id],
        )
        return uploaded_images

    @classmethod
    async def _stage_image_from_bytes(
        cls,
        image_content: bytes,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> tuple[dict, bool]:
        """Stage one image link without crossing the caller's commit boundary."""

        product = await session.get(Product, product_id)
        if not product:
            raise LookupError("Product not found")
        try:
            original = await ProductOriginalMediaService.save_shared_original(image_content)
        except Exception as exc:
            logger.error("Failed to process image: %s", exc)
            raise ValueError("Invalid image file") from exc

        relative_url = original.url
        existing_link = (
            await session.execute(
                select(ProductImage).where(
                    ProductImage.product_id == product_id,
                    ProductImage.url == relative_url,
                )
            )
        ).scalar_one_or_none()

        changed = existing_link is None
        if existing_link is None:
            image = ProductImage(
                product_id=product_id,
                url=relative_url,
                is_installation_photo=is_installation,
            )
            session.add(image)
        else:
            image = existing_link
        await session.flush()

        original_variant = (
            await session.execute(
                select(ProductImageVariant).where(
                    ProductImageVariant.product_image_id == image.id,
                    ProductImageVariant.variant_type
                    == ProductImageVariantType.ORIGINAL.value,
                )
            )
        ).scalar_one_or_none()
        if (
            original_variant is None
            or not original_variant.url
            or original_variant.processing_status
            != ProductImageProcessingStatus.READY.value
        ):
            await ProductImageVariantService.ensure_original_variant(
                session,
                image,
                source_content=original.content,
                extension="webp",
                width=original.width,
                height=original.height,
            )
            changed = True

        if set_main and not is_installation and product.main_image != relative_url:
            product.main_image = relative_url
            session.add(product)
            changed = True

        changed = await cls._sync_legacy_images(session, product_id) or changed
        return {"url": relative_url, "id": image.id}, changed

    @staticmethod
    async def _sync_legacy_images(session: AsyncSession, product_id: int) -> bool:
        """Sync ProductImage links to the legacy Product.images JSON list."""

        product = await session.get(Product, product_id)
        if not product:
            return False
        images = (
            await session.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.id)
            )
        ).scalars().all()
        next_images = [image.url for image in images if not image.is_installation_photo]
        if list(product.images or []) == next_images:
            return False
        product.images = next_images
        session.add(product)
        return True


    @staticmethod
    def local_media_path_for_url(url: str) -> Path | None:
        if not url:
            return None
        if url.startswith("/media/"):
            return Path(url.lstrip("/"))
        if url.startswith("media/"):
            return Path(url)
        return None

    @classmethod
    async def load_image_source_content(cls, url: str) -> bytes:
        source_path = cls.local_media_path_for_url(url)
        if source_path is not None and source_path.exists():
            return await asyncio.to_thread(source_path.read_bytes)

        if url.startswith("http://") or url.startswith("https://"):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.get(url, timeout=15.0)
                    response.raise_for_status()
                    return response.content
            except Exception as exc:
                logger.error("Failed to download source image for crop: %s", exc)
                raise ValueError("Source image is not available") from exc

        raise ValueError("Source image is not available in local media storage")

    @staticmethod
    def crop_image_bytes(
        content: bytes,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> bytes:
        if not content:
            raise ValueError("Source image is empty")
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            left = max(0, min(int(x), image.width - 1))
            top = max(0, min(int(y), image.height - 1))
            right = max(left + 1, min(left + int(width), image.width))
            bottom = max(top + 1, min(top + int(height), image.height))
            cropped = image.crop((left, top, right, bottom))
            if cropped.mode in {"RGBA", "P"}:
                cropped = cropped.convert("RGB")
            output = BytesIO()
            cropped.save(output, format="PNG")
            return output.getvalue()

    @staticmethod
    async def cleanup_media(session: AsyncSession, *, dry_run: bool = False) -> dict:
        """Report orphan candidates; physical GC is disabled until coordinated."""

        if not dry_run:
            raise RuntimeError(
                "Physical media GC is deferred until writer synchronization is available"
            )

        base_dir = os.path.join("media", "products")
        if not os.path.exists(base_dir):
            return {
                "dry_run": True,
                "deleted_count": 0,
                "reclaimed_bytes": 0,
                "files": [],
            }

        known_urls = set(
            (
                await session.execute(
                    select(Product.main_image).where(Product.main_image != None)  # noqa: E711
                )
            ).scalars().all()
        )
        known_urls.update(
            (await session.execute(select(ProductImage.url))).scalars().all()
        )
        known_urls.update(
            (
                await session.execute(
                    select(ProductImageVariant.url).where(
                        ProductImageVariant.url != None  # noqa: E711
                    )
                )
            ).scalars().all()
        )

        deleted_count = 0
        reclaimed_bytes = 0
        report = []
        for root, _, files in os.walk(base_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                db_path_rel = os.path.join(root, file_name)
                db_path_abs = "/" + db_path_rel
                if db_path_abs in known_urls or db_path_rel in known_urls:
                    continue
                size = os.path.getsize(full_path)
                deleted_count += 1
                reclaimed_bytes += size
                report.append(db_path_abs)

        return {
            "dry_run": True,
            "deleted_count": deleted_count,
            "reclaimed_bytes": reclaimed_bytes,
            "files": report[:50],
        }
