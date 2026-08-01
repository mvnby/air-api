"""Service-layer helpers for manager media/search workflows."""

import asyncio
import os
from io import BytesIO
from pathlib import Path
from typing import List, Set

import httpx
from core.logger import logger
from duckduckgo_search import DDGS
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select, update

from models import Product, ProductImage, ProductImageVariant, ProductSeries
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.product_image_processing_contract import ProductImageVariantType
from services.product_image_processing_provider import (
    ProductImageProcessingContext,
    get_product_image_processor,
)
from services.product_original_media_service import ProductOriginalMediaService
from services.product_image_variant_service import ProductImageVariantService


class ManagerMediaService:
    @staticmethod
    async def set_main_image(session: AsyncSession, image_id: int) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        product = await session.get(Product, image.product_id)
        if not product:
            raise ValueError("Product not found")

        statement = update(Product).where(Product.id == product.id).values(main_image=image.url)
        await session.execute(statement)
        await session.commit()
        return {"message": "Main image updated", "url": image.url}

    @staticmethod
    async def delete_gallery_image(session: AsyncSession, image_id: int) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        image_url = image.url
        product = await session.get(Product, image.product_id)
        if product and product.main_image == image.url:
            statement = update(Product).where(Product.id == product.id).values(main_image=None)
            await session.execute(statement)

        variant_rows = (
            await session.execute(
                select(ProductImageVariant).where(ProductImageVariant.product_image_id == image.id)
            )
        ).scalars().all()
        variant_urls = [variant.url for variant in variant_rows if variant.url]
        for variant in variant_rows:
            await session.delete(variant)

        await session.delete(image)
        await session.flush()
        if product:
            await ManagerMediaService.sync_legacy_images(session, product.id)

        await session.commit()
        await ManagerMediaService.remove_file_if_unreferenced(session, image_url)
        for variant_url in variant_urls:
            await ManagerMediaService.remove_file_if_unreferenced(session, variant_url)
        return {"message": "Image deleted"}

    @staticmethod
    async def crop_gallery_image(
        session: AsyncSession,
        image_id: int,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        mode: str = "append",
        set_main: bool = False,
    ) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        product = await session.get(Product, image.product_id)
        if not product:
            raise ValueError("Product not found")

        try:
            source_content = await ManagerMediaService.load_image_source_content(image.url)
            cropped_content = await asyncio.to_thread(
                ManagerMediaService.crop_image_bytes,
                source_content,
                x,
                y,
                width,
                height,
            )
        except UnidentifiedImageError as exc:
            raise ValueError("Source image cannot be opened") from exc

        normalized_mode = mode if mode in {"append", "replace"} else "append"
        if normalized_mode == "append":
            return await ManagerMediaService.save_image_from_bytes(
                image_content=cropped_content,
                product_id=product.id,
                session=session,
                set_main=set_main and not image.is_installation_photo,
                is_installation=image.is_installation_photo,
            )

        old_url = image.url
        was_main = product.main_image == old_url
        original = await ProductOriginalMediaService.save_shared_original(cropped_content)

        variant_rows = (
            await session.execute(
                select(ProductImageVariant).where(ProductImageVariant.product_image_id == image.id)
            )
        ).scalars().all()
        for variant in variant_rows:
            await session.delete(variant)

        image.url = original.url
        session.add(image)
        await session.flush()
        await ProductImageVariantService.ensure_original_variant(
            session,
            image,
            source_content=original.content,
            extension="webp",
            width=original.width,
            height=original.height,
        )

        if (was_main or set_main) and not image.is_installation_photo:
            product.main_image = original.url
            session.add(product)

        await ManagerMediaService.sync_legacy_images(session, product.id)
        await session.commit()
        await session.refresh(image)

        return {"id": image.id, "url": image.url}

    @staticmethod
    async def remove_background_gallery_image(
        session: AsyncSession,
        image_id: int,
        *,
        provider: str = "auto",
        rembg_model: str | None = None,
        mode: str = "replace",
        set_main: bool = False,
    ) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        product = await session.get(Product, image.product_id)
        if not product:
            raise ValueError("Product not found")

        source_content = await ManagerMediaService.load_image_source_content(image.url)
        processor = get_product_image_processor(provider, rembg_model=rembg_model)
        processed = await processor.process(
            source_content=source_content,
            context=ProductImageProcessingContext(
                product_image_id=image.id,
                source_url=image.url,
                variant_type=ProductImageVariantType.PROCESSED.value,
            ),
        )

        normalized_mode = mode if mode in {"append", "replace"} else "replace"
        if normalized_mode == "append":
            return await ManagerMediaService.save_image_from_bytes(
                image_content=processed.content,
                product_id=product.id,
                session=session,
                set_main=set_main and not image.is_installation_photo,
                is_installation=image.is_installation_photo,
            )

        old_url = image.url
        was_main = product.main_image == old_url
        original = await ProductOriginalMediaService.save_shared_original(processed.content)

        variant_rows = (
            await session.execute(
                select(ProductImageVariant).where(ProductImageVariant.product_image_id == image.id)
            )
        ).scalars().all()
        variant_urls = [variant.url for variant in variant_rows if variant.url]
        for variant in variant_rows:
            await session.delete(variant)

        image.url = original.url
        session.add(image)
        await session.flush()
        await ProductImageVariantService.ensure_original_variant(
            session,
            image,
            source_content=original.content,
            extension="webp",
            width=original.width,
            height=original.height,
        )

        if (was_main or set_main) and not image.is_installation_photo:
            product.main_image = original.url
            session.add(product)

        await ManagerMediaService.sync_legacy_images(session, product.id)
        await session.commit()
        await session.refresh(image)

        return {"id": image.id, "url": image.url}

    @staticmethod
    async def search_reuse_products(session: AsyncSession, query: str, limit: int = 10) -> List[dict]:
        statement = select(Product).where(Product.title.ilike(f"%{query}%")).limit(limit)
        result = await session.execute(statement)
        products = result.scalars().all()
        return [{"id": p.id, "title": p.title, "main_image": p.main_image} for p in products]

    @staticmethod
    async def reuse_image_link(session: AsyncSession, product_id: int, source_image_url: str) -> dict:
        product = await session.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")

        existing_stmt = select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.url == source_image_url,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            await ProductImageVariantService.ensure_original_variant(session, existing)
            await session.commit()
            return {"message": "Image already linked", "id": existing.id}

        new_image = ProductImage(
            product_id=product_id,
            url=source_image_url,
            is_installation_photo=False,
        )
        session.add(new_image)
        await session.flush()
        await ProductImageVariantService.ensure_original_variant(session, new_image)
        await ManagerMediaService.sync_legacy_images(session, product_id)
        await session.commit()
        return {"message": "Image linked", "id": new_image.id}

    @staticmethod
    async def search_images(query: str, max_results: int = 20) -> List[dict]:
        """
        Search images in DuckDuckGo and return normalized lightweight payload.
        Returns empty list on provider errors/rate limits for graceful degradation.
        """
        try:
            results = await asyncio.to_thread(
                lambda: list(DDGS().images(query, max_results=max_results))
            )
        except Exception as exc:
            if "Ratelimit" in str(exc) or "403" in str(exc):
                logger.warning(f"DDG Ratelimit hit for query: {query}")
            else:
                logger.warning(f"Image search provider error (DDG): {exc}")
            return []

        images = []
        for result in results:
            if result.get("image"):
                images.append(
                    {
                        "image": result.get("image"),
                        "width": result.get("width"),
                        "height": result.get("height"),
                        "thumbnail": result.get("thumbnail"),
                    }
                )
        return images

    @staticmethod
    async def process_and_save_image(
        url: str,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Download image by URL and persist it to gallery storage."""
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                image_content = response.content
        except Exception as exc:
            logger.warning(f"Failed to download external image: {exc}")
            raise ValueError(f"Failed to download image: {exc}") from exc

        return await ManagerMediaService.save_image_from_bytes(
            image_content=image_content,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )

    @staticmethod
    async def save_image_from_bytes(
        image_content: bytes,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Process bytes, deduplicate storage by hash, and attach ProductImage link."""
        try:
            original = await ProductOriginalMediaService.save_shared_original(image_content)
        except Exception as exc:
            logger.error(f"Failed to process image: {exc}")
            raise ValueError("Invalid image file") from exc

        relative_url = original.url
        existing_stmt = select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.url == relative_url,
        )
        existing_result = await session.execute(existing_stmt)
        existing_link = existing_result.scalar_one_or_none()

        if existing_link is None:
            new_image = ProductImage(
                product_id=product_id,
                url=relative_url,
                is_installation_photo=is_installation,
            )
            session.add(new_image)
        else:
            new_image = existing_link
        await session.flush()
        await ProductImageVariantService.ensure_original_variant(
            session,
            new_image,
            source_content=original.content,
            extension="webp",
            width=original.width,
            height=original.height,
        )

        if set_main and not is_installation:
            statement = update(Product).where(Product.id == product_id).values(main_image=relative_url)
            await session.execute(statement)

        await ManagerMediaService.sync_legacy_images(session, product_id)
        await session.commit()
        await session.refresh(new_image)

        return {"url": relative_url, "id": new_image.id}

    @staticmethod
    async def sync_legacy_images(session: AsyncSession, product_id: int) -> None:
        """Sync ProductImage links to legacy Product.images JSON list."""
        product = await session.get(Product, product_id)
        if not product:
            return

        stmt = select(ProductImage).where(ProductImage.product_id == product_id)
        result = await session.execute(stmt)
        images = result.scalars().all()

        product.images = [img.url for img in images if not img.is_installation_photo]
        session.add(product)

    @staticmethod
    async def remove_file_if_unreferenced(session: AsyncSession, url: str) -> bool:
        """Delete physical file only when no ProductImage/Product.main_image references remain."""
        gallery_ref_stmt = select(func.count()).select_from(ProductImage).where(ProductImage.url == url)
        gallery_refs = (await session.execute(gallery_ref_stmt)).scalar_one()

        main_ref_stmt = select(func.count()).select_from(Product).where(Product.main_image == url)
        main_refs = (await session.execute(main_ref_stmt)).scalar_one()

        variant_ref_stmt = select(func.count()).select_from(ProductImageVariant).where(
            ProductImageVariant.url == url
        )
        variant_refs = (await session.execute(variant_ref_stmt)).scalar_one()

        if gallery_refs > 0 or main_refs > 0 or variant_refs > 0:
            return False
        if not url.startswith("/media/"):
            return False

        path = url.lstrip("/")
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except Exception as exc:
                logger.error(f"Failed to delete unreferenced file {url}: {exc}")
        return False

    @staticmethod
    def local_media_path_for_url(url: str) -> Path | None:
        if not url:
            return None
        if url.startswith("/media/"):
            return Path(url.lstrip("/"))
        if url.startswith("media/"):
            return Path(url)
        return None

    @staticmethod
    async def load_image_source_content(url: str) -> bytes:
        source_path = ManagerMediaService.local_media_path_for_url(url)
        if source_path is not None and source_path.exists():
            return await asyncio.to_thread(source_path.read_bytes)

        if url.startswith("http://") or url.startswith("https://"):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.get(url, timeout=15.0)
                    response.raise_for_status()
                    return response.content
            except Exception as exc:
                logger.error(f"Failed to download source image for crop: {exc}")
                raise ValueError("Source image is not available") from exc

        raise ValueError("Source image is not available in local media storage")

    @staticmethod
    def crop_image_bytes(content: bytes, x: int, y: int, width: int, height: int) -> bytes:
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
    async def get_common_gallery_urls(
        session: AsyncSession,
        product_ids: List[int],
        *,
        exclude_installation: bool = True,
    ) -> Set[str]:
        """Get image URLs present in all selected products."""
        if not product_ids:
            return set()

        stmt = select(ProductImage).where(ProductImage.product_id.in_(product_ids))
        if exclude_installation:
            stmt = stmt.where(ProductImage.is_installation_photo == False)  # noqa: E712

        rows = (await session.execute(stmt)).scalars().all()
        by_url = {}
        target_ids = set(product_ids)
        for row in rows:
            by_url.setdefault(row.url, set()).add(row.product_id)
        return {url for url, linked in by_url.items() if linked == target_ids}

    @staticmethod
    async def bulk_add_gallery_images(
        session: AsyncSession,
        *,
        product_ids: List[int],
        source_urls: List[str],
        is_installation: bool,
        skip_existing: bool,
        set_main: bool,
        commit: bool = True,
    ) -> dict:
        if not product_ids:
            raise ValueError("product_ids is required")
        if not source_urls:
            raise ValueError("source_urls is required")

        unique_product_ids = list(dict.fromkeys(product_ids))
        unique_urls = [url for url in dict.fromkeys(source_urls) if url]
        if not unique_urls:
            raise ValueError("No valid source_urls provided")

        products_stmt = select(Product.id).where(Product.id.in_(unique_product_ids))
        existing_product_ids = set((await session.execute(products_stmt)).scalars().all())
        missing = sorted(set(unique_product_ids) - existing_product_ids)
        if missing:
            raise LookupError(f"Products not found: {missing}")

        added = 0
        skipped = 0
        first_url = unique_urls[0]

        for product_id in unique_product_ids:
            for url in unique_urls:
                existing_stmt = select(ProductImage.id).where(
                    ProductImage.product_id == product_id,
                    ProductImage.url == url,
                )
                existing = (await session.execute(existing_stmt)).scalar_one_or_none()
                if existing and skip_existing:
                    skipped += 1
                    continue
                if not existing:
                    image = ProductImage(
                        product_id=product_id,
                        url=url,
                        is_installation_photo=is_installation,
                    )
                    session.add(image)
                    await session.flush()
                    await ProductImageVariantService.ensure_original_variant(session, image)
                    added += 1
                else:
                    skipped += 1

            if set_main and not is_installation:
                product = await session.get(Product, product_id)
                if product:
                    product.main_image = first_url
                    session.add(product)

            await ManagerMediaService.sync_legacy_images(session, product_id)

        if commit:
            await session.commit()
        return {
            "message": "Bulk image add completed",
            "products_count": len(unique_product_ids),
            "added_links": added,
            "skipped_existing": skipped,
        }

    @staticmethod
    async def bulk_delete_common_gallery_images(
        session: AsyncSession,
        *,
        product_ids: List[int],
        urls: List[str],
        exclude_installation: bool,
    ) -> dict:
        if not product_ids:
            raise ValueError("product_ids is required")
        if not urls:
            raise ValueError("urls is required")

        unique_product_ids = list(dict.fromkeys(product_ids))
        unique_urls = [url for url in dict.fromkeys(urls) if url]
        if not unique_urls:
            raise ValueError("No valid urls provided")

        common_urls = await ManagerMediaService.get_common_gallery_urls(
            session=session,
            product_ids=unique_product_ids,
            exclude_installation=exclude_installation,
        )
        invalid_urls = [url for url in unique_urls if url not in common_urls]
        if invalid_urls:
            raise ValueError(
                {
                    "message": "Only common images can be deleted in bulk mode",
                    "not_common": invalid_urls,
                }
            )

        deleted_links = 0
        for product_id in unique_product_ids:
            stmt = select(ProductImage).where(
                ProductImage.product_id == product_id,
                ProductImage.url.in_(unique_urls),
            )
            if exclude_installation:
                stmt = stmt.where(ProductImage.is_installation_photo == False)  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            row_ids = [row.id for row in rows if row.id is not None]
            if row_ids:
                variant_rows = (
                    await session.execute(
                        select(ProductImageVariant).where(
                            ProductImageVariant.product_image_id.in_(row_ids)
                        )
                    )
                ).scalars().all()
                for variant in variant_rows:
                    await session.delete(variant)
            for row in rows:
                await session.delete(row)
                deleted_links += 1

            product = await session.get(Product, product_id)
            if product and product.main_image in unique_urls:
                product.main_image = None
                session.add(product)

            await ManagerMediaService.sync_legacy_images(session, product_id)

        await session.commit()

        for url in unique_urls:
            await ManagerMediaService.remove_file_if_unreferenced(session, url)

        return {
            "message": "Bulk delete completed",
            "products_count": len(unique_product_ids),
            "deleted_links": deleted_links,
        }

    @staticmethod
    async def apply_gallery_to_series(
        session: AsyncSession,
        product_id: int,
        *,
        dry_run: bool = False,
        delete_unreferenced: bool = False,
    ) -> dict:
        source_product = await session.get(Product, product_id)
        if not source_product:
            raise LookupError("Product not found")
        if not source_product.series_id:
            raise ValueError("Product is not assigned to a series")

        series = await session.get(ProductSeries, source_product.series_id)

        source_rows = (
            await session.execute(
                select(ProductImage)
                .where(
                    ProductImage.product_id == source_product.id,
                    ProductImage.is_installation_photo == False,  # noqa: E712
                )
                .order_by(ProductImage.id)
            )
        ).scalars().all()

        source_urls: list[str] = []
        if source_product.main_image:
            source_urls.append(source_product.main_image)
        source_urls.extend(image.url for image in source_rows)
        source_urls = [url for url in dict.fromkeys(source_urls) if url]
        if not source_urls:
            raise ValueError("Source product has no non-installation gallery images")

        target_products = (
            await session.execute(
                select(Product).where(
                    Product.series_id == source_product.series_id,
                    Product.id != source_product.id,
                )
            )
        ).scalars().all()

        updated_products = 0
        preserved_installation_links = 0
        replaced_links = 0
        obsolete_urls: list[str] = []
        obsolete_variant_urls: list[str] = []

        target_rows_by_product_id: dict[int, list[ProductImage]] = {}
        for target_product in target_products:
            target_rows = (
                await session.execute(
                    select(ProductImage).where(ProductImage.product_id == target_product.id)
                )
            ).scalars().all()
            target_rows_by_product_id[target_product.id] = list(target_rows)
            old_gallery_rows = [row for row in target_rows if not row.is_installation_photo]
            replaced_links += len(old_gallery_rows)
            obsolete_urls.extend(row.url for row in old_gallery_rows if row.url and row.url not in source_urls)
            preserved_installation_links += len({row.url for row in target_rows if row.is_installation_photo})

            old_gallery_ids = [row.id for row in old_gallery_rows if row.id is not None]
            if old_gallery_ids:
                variant_urls = (
                    await session.execute(
                        select(ProductImageVariant.url).where(
                            ProductImageVariant.product_image_id.in_(old_gallery_ids),
                            ProductImageVariant.url != None,  # noqa: E711
                        )
                    )
                ).scalars().all()
                obsolete_variant_urls.extend(url for url in variant_urls if url)

        obsolete_urls = list(dict.fromkeys(obsolete_urls))

        if dry_run:
            return {
                "message": "Series gallery preview",
                "dry_run": True,
                "source_product_id": source_product.id,
                "series_id": source_product.series_id,
                "series_title": series.title if series else None,
                "updated_products": len(target_products),
                "images_applied": len(source_urls),
                "main_image": source_product.main_image,
                "replaced_links": replaced_links,
                "obsolete_urls": obsolete_urls,
                "preserved_installation_links": preserved_installation_links,
                "deleted_files_count": 0,
            }

        if series:
            series.gallery_images = list(dict.fromkeys([*(series.gallery_images or []), *source_urls]))
            session.add(series)

        for target_product in target_products:
            target_rows = target_rows_by_product_id[target_product.id]

            old_gallery_rows = [row for row in target_rows if not row.is_installation_photo]
            installation_urls = {row.url for row in target_rows if row.is_installation_photo}

            old_gallery_ids = [row.id for row in old_gallery_rows if row.id is not None]
            if old_gallery_ids:
                variant_rows = (
                    await session.execute(
                        select(ProductImageVariant).where(
                            ProductImageVariant.product_image_id.in_(old_gallery_ids)
                        )
                    )
                ).scalars().all()
                for variant in variant_rows:
                    await session.delete(variant)

            for row in old_gallery_rows:
                await session.delete(row)
            await session.flush()

            for url in source_urls:
                if url in installation_urls:
                    continue
                image = ProductImage(
                    product_id=target_product.id,
                    url=url,
                    is_installation_photo=False,
                )
                session.add(image)
                await session.flush()
                await ProductImageVariantService.ensure_original_variant(session, image)

            target_product.main_image = source_product.main_image
            session.add(target_product)
            await ManagerMediaService.sync_legacy_images(session, target_product.id)
            updated_products += 1

        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="product_series_gallery_apply",
            product_ids=[source_product.id, *(product.id for product in target_products)],
        )

        deleted_files_count = 0
        if delete_unreferenced:
            for url in dict.fromkeys([*obsolete_urls, *obsolete_variant_urls]):
                deleted = await ManagerMediaService.remove_file_if_unreferenced(session, url)
                if deleted:
                    deleted_files_count += 1

        return {
            "message": "Series gallery applied",
            "dry_run": False,
            "source_product_id": source_product.id,
            "series_id": source_product.series_id,
            "series_title": series.title if series else None,
            "updated_products": updated_products,
            "images_applied": len(source_urls),
            "main_image": source_product.main_image,
            "replaced_links": replaced_links,
            "obsolete_urls": obsolete_urls,
            "preserved_installation_links": preserved_installation_links,
            "deleted_files_count": deleted_files_count,
        }

    @staticmethod
    async def bulk_upload_local_images(
        session: AsyncSession,
        *,
        product_ids: List[int],
        file_payloads: List[bytes],
        is_installation: bool,
        set_main: bool,
    ) -> dict:
        if not product_ids:
            raise ValueError("product_ids is required")
        if not file_payloads:
            raise ValueError("No valid files uploaded")

        unique_product_ids = list(dict.fromkeys(product_ids))

        products_stmt = select(Product.id).where(Product.id.in_(unique_product_ids))
        existing_product_ids = set((await session.execute(products_stmt)).scalars().all())
        missing = sorted(set(unique_product_ids) - existing_product_ids)
        if missing:
            raise LookupError(f"Products not found: {missing}")

        uploaded = 0
        for product_id in unique_product_ids:
            for idx, content in enumerate(file_payloads):
                should_set_main = set_main and idx == 0 and not is_installation
                await ManagerMediaService.save_image_from_bytes(
                    image_content=content,
                    product_id=product_id,
                    session=session,
                    set_main=should_set_main,
                    is_installation=is_installation,
                )
                uploaded += 1

        return {
            "message": "Bulk upload completed",
            "products_count": len(unique_product_ids),
            "files_count": len(file_payloads),
            "uploaded_links": uploaded,
        }

    @staticmethod
    async def cleanup_media(session: AsyncSession, *, dry_run: bool = False) -> dict:
        """Delete orphaned product media files not referenced in DB."""
        stmt_main = select(Product.main_image).where(Product.main_image != None)
        res_main = await session.execute(stmt_main)
        known_urls = set(res_main.scalars().all())

        stmt_gallery = select(ProductImage.url)
        res_gallery = await session.execute(stmt_gallery)
        known_urls.update(res_gallery.scalars().all())

        stmt_variants = select(ProductImageVariant.url).where(ProductImageVariant.url != None)
        res_variants = await session.execute(stmt_variants)
        known_urls.update(res_variants.scalars().all())

        base_dir = os.path.join("media", "products")
        deleted_count = 0
        reclaimed_bytes = 0

        if not os.path.exists(base_dir):
            return {"message": "Media directory not found", "deleted": 0}

        report = []
        for root, _, files in os.walk(base_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                db_path_rel = os.path.join(root, file_name)
                db_path_abs = "/" + db_path_rel

                if db_path_abs not in known_urls and db_path_rel not in known_urls:
                    size = os.path.getsize(full_path)
                    if not dry_run:
                        os.remove(full_path)

                    deleted_count += 1
                    reclaimed_bytes += size
                    report.append(db_path_abs)

        return {
            "dry_run": dry_run,
            "deleted_count": deleted_count,
            "reclaimed_bytes": reclaimed_bytes,
            "files": report[:50],
        }
