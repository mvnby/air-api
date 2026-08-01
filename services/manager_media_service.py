"""Service-layer helpers for manager media/search workflows."""

import asyncio
from typing import List, Set

from PIL import UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from models import Product, ProductImage, ProductImageVariant, ProductSeries
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.catalog_mutation_contracts import CatalogMutationBatch
from services.manager_media_storage_service import ManagerMediaStorageOperations
from services.product_image_processing_contract import ProductImageVariantType
from services.product_image_processing_provider import (
    ProductImageProcessingContext,
    get_product_image_processor,
)
from services.product_original_media_service import ProductOriginalMediaService
from services.product_image_variant_service import ProductImageVariantService


class ManagerMediaService(ManagerMediaStorageOperations):
    @staticmethod
    async def set_main_image(session: AsyncSession, image_id: int) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        product = await session.get(Product, image.product_id)
        if not product:
            raise ValueError("Product not found")

        changed = product.main_image != image.url
        if changed:
            product.main_image = image.url
            session.add(product)
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.set_main_image",
            changed=changed,
            product_ids=[product.id],
        )
        return {"message": "Main image updated", "url": image.url}

    @staticmethod
    async def delete_gallery_image(session: AsyncSession, image_id: int) -> dict:
        image = await session.get(ProductImage, image_id)
        if not image:
            raise ValueError("Image not found")

        product = await session.get(Product, image.product_id)
        if product and product.main_image == image.url:
            statement = update(Product).where(Product.id == product.id).values(main_image=None)
            await session.execute(statement)

        variant_rows = (
            await session.execute(
                select(ProductImageVariant).where(ProductImageVariant.product_image_id == image.id)
            )
        ).scalars().all()
        for variant in variant_rows:
            await session.delete(variant)

        await session.delete(image)
        await session.flush()
        if product:
            await ManagerMediaService._sync_legacy_images(session, product.id)

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.delete_gallery_image",
            changed=True,
            product_ids=[image.product_id],
        )
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
            result, changed = await ManagerMediaService._stage_image_from_bytes(
                image_content=cropped_content,
                product_id=product.id,
                session=session,
                set_main=set_main and not image.is_installation_photo,
                is_installation=image.is_installation_photo,
            )
            await CatalogInvalidationCommitService.commit_registered_global_mutation(
                session,
                producer="manager_media.crop_gallery_image",
                changed=changed,
                product_ids=[product.id],
            )
            return result

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

        await ManagerMediaService._sync_legacy_images(session, product.id)
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.crop_gallery_image",
            changed=True,
            product_ids=[product.id],
        )
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
            result, changed = await ManagerMediaService._stage_image_from_bytes(
                image_content=processed.content,
                product_id=product.id,
                session=session,
                set_main=set_main and not image.is_installation_photo,
                is_installation=image.is_installation_photo,
            )
            await CatalogInvalidationCommitService.commit_registered_global_mutation(
                session,
                producer="manager_media.remove_background_gallery_image",
                changed=changed,
                product_ids=[product.id],
            )
            return result

        old_url = image.url
        was_main = product.main_image == old_url
        original = await ProductOriginalMediaService.save_shared_original(processed.content)

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

        await ManagerMediaService._sync_legacy_images(session, product.id)
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.remove_background_gallery_image",
            changed=True,
            product_ids=[product.id],
        )
        await session.refresh(image)

        return {"id": image.id, "url": image.url}

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
        mutation_batch: CatalogMutationBatch | None = None,
    ) -> dict:
        if not commit and mutation_batch is None:
            raise ValueError("commit=False requires a caller-owned mutation_batch")
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
        changed = False
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
                    changed = True
                else:
                    skipped += 1

            if set_main and not is_installation:
                product = await session.get(Product, product_id)
                if product and product.main_image != first_url:
                    product.main_image = first_url
                    session.add(product)
                    changed = True

            changed = (
                await ManagerMediaService._sync_legacy_images(session, product_id)
                or changed
            )

        if commit:
            await CatalogInvalidationCommitService.commit_registered_global_mutation(
                session,
                producer="manager_media.bulk_add_gallery_images",
                changed=changed,
                product_ids=unique_product_ids,
            )
        else:
            assert mutation_batch is not None
            mutation_batch.record(
                changed=changed,
                product_ids=unique_product_ids,
            )
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

            await ManagerMediaService._sync_legacy_images(session, product_id)

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.bulk_delete_common_gallery_images",
            changed=deleted_links > 0,
            product_ids=unique_product_ids,
        )

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
        if delete_unreferenced:
            raise RuntimeError(
                "Physical media cleanup is deferred; retry without delete_unreferenced"
            )

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

        target_rows_by_product_id: dict[int, list[ProductImage]] = {}
        for target_product in target_products:
            target_rows = (
                await session.execute(
                    select(ProductImage)
                    .where(ProductImage.product_id == target_product.id)
                    .order_by(ProductImage.id)
                )
            ).scalars().all()
            target_rows_by_product_id[target_product.id] = list(target_rows)
            old_gallery_rows = [row for row in target_rows if not row.is_installation_photo]
            replaced_links += len(old_gallery_rows)
            obsolete_urls.extend(row.url for row in old_gallery_rows if row.url and row.url not in source_urls)
            preserved_installation_links += len({row.url for row in target_rows if row.is_installation_photo})

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

        changed = False
        if series:
            next_series_gallery = list(
                dict.fromkeys([*(series.gallery_images or []), *source_urls])
            )
            if list(series.gallery_images or []) != next_series_gallery:
                series.gallery_images = next_series_gallery
                session.add(series)
                changed = True

        for target_product in target_products:
            target_rows = target_rows_by_product_id[target_product.id]

            old_gallery_rows = [row for row in target_rows if not row.is_installation_photo]
            installation_urls = {row.url for row in target_rows if row.is_installation_photo}
            desired_gallery_urls = [url for url in source_urls if url not in installation_urls]
            if (
                [row.url for row in old_gallery_rows] == desired_gallery_urls
                and target_product.main_image == source_product.main_image
            ):
                continue

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
            await ManagerMediaService._sync_legacy_images(session, target_product.id)
            updated_products += 1
            changed = True

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.apply_gallery_to_series",
            changed=changed,
            product_ids=[source_product.id, *(product.id for product in target_products)],
        )

        # Physical object deletion is intentionally deferred to a future durable
        # GC. Request paths must never race a concurrent content-addressed writer.
        deleted_files_count = 0

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
        changed = False
        for product_id in unique_product_ids:
            for idx, content in enumerate(file_payloads):
                should_set_main = set_main and idx == 0 and not is_installation
                _, image_changed = await ManagerMediaService._stage_image_from_bytes(
                    image_content=content,
                    product_id=product_id,
                    session=session,
                    set_main=should_set_main,
                    is_installation=is_installation,
                )
                uploaded += 1
                changed = changed or image_changed

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.bulk_upload_local_images",
            changed=changed,
            product_ids=unique_product_ids,
        )

        return {
            "message": "Bulk upload completed",
            "products_count": len(unique_product_ids),
            "files_count": len(file_payloads),
            "uploaded_links": uploaded,
        }
