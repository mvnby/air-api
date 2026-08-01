"""Write-oriented product service operations (mutations/updates)."""

from copy import deepcopy
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from slugify import slugify

from crud.product import ProductDAO
from models import Product, ProductImage, Tag
from services.brand_series_service import sync_product_brand_series
from services.catalog_revision_service import CatalogRevisionService
from services.product_attachment_service import replace_manuals
from services.product_kind_service import ProductKindService
from services.spec_normalizer import normalize_specs
from services.product_supply_metrics_service import ProductSupplyMetricsService


class ProductWriteService:
    @staticmethod
    async def _unique_slug(
        session: AsyncSession,
        *,
        requested_slug: Optional[str],
        title: str,
    ) -> str:
        base = slugify(str(requested_slug or "").strip(), lowercase=True)
        if not base:
            base = slugify(str(title or "").strip(), lowercase=True)
        if not base:
            raise ValueError("Не удалось сформировать slug товара.")

        candidate = base
        suffix = 2
        while True:
            existing = (
                await session.execute(select(Product.id).where(Product.slug == candidate))
            ).scalar_one_or_none()
            if existing is None:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    @staticmethod
    async def _resolve_tags(session: AsyncSession, tag_ids: Optional[List[int]]) -> List[Tag]:
        if not tag_ids:
            return []
        rows = (
            await session.execute(
                select(Tag).where(Tag.id.in_(tag_ids)).options(selectinload(Tag.group))
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _wifi_tag_slugs(tags: List[Tag]) -> List[str]:
        return [tag.slug for tag in tags if tag.slug in {"wifi-builtin", "wifi-ready"}]

    @staticmethod
    async def create_product(
        session: AsyncSession,
        create_data: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        payload = dict(create_data)
        manuals_payload = payload.pop("manuals", [])
        selected_tags = await ProductWriteService._resolve_tags(session, tag_ids)
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Название товара обязательно.")

        slug = await ProductWriteService._unique_slug(
            session,
            requested_slug=payload.get("slug"),
            title=title,
        )
        specs = normalize_specs(
            deepcopy(payload.get("specs") or {}),
            wifi_tag_slugs=ProductWriteService._wifi_tag_slugs(selected_tags),
            strict_wifi_from_tags=False,
            title=title,
        )

        product = Product(
            title=title,
            slug=slug,
            description=str(payload.get("description") or ""),
            price=int(payload.get("price") or 0),
            old_price=payload.get("old_price"),
            product_kind=ProductKindService.resolve(
                payload.get("product_kind"),
                specs=specs,
            ),
            is_inverter=bool(payload.get("is_inverter", False)),
            power_cooling=payload.get("power_cooling"),
            main_image=payload.get("main_image"),
            images=[],
            tags=selected_tags,
            specs=specs,
            is_published=bool(payload.get("is_published", True)),
            source_url=payload.get("source_url"),
            brand_id=payload.get("brand_id"),
            series_id=payload.get("series_id"),
        )
        session.add(product)
        await session.flush()

        await replace_manuals(
            session,
            product_id=product.id,
            manuals=manuals_payload,
        )
        await sync_product_brand_series(
            session,
            product=product,
            specs=specs,
            title=title,
            tags=selected_tags,
            explicit_brand_id=payload.get("brand_id"),
            explicit_brand_override="brand_id" in payload,
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="product_create",
            product_ids=[product.id],
            slugs=[product.slug],
        )
        await session.commit()
        return {"message": "Product created", "id": product.id}

    @staticmethod
    async def duplicate_product(
        session: AsyncSession,
        source_product_id: int,
        overrides: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
        *,
        copy_gallery: bool = True,
        copy_manuals: bool = True,
        copy_tags: bool = True,
        make_unpublished: bool = False,
    ) -> Optional[Dict[str, Any]]:
        source = await ProductDAO.get_by_id(session, source_product_id)
        if not source:
            return None

        payload = dict(overrides)
        manuals_payload = payload.pop("manuals", None)
        title = str(payload.get("title") or source.title or "").strip()
        if not title:
            raise ValueError("Название товара обязательно.")

        if tag_ids is not None:
            selected_tags = await ProductWriteService._resolve_tags(session, tag_ids)
        elif copy_tags:
            selected_tags = list(source.tags or [])
        else:
            selected_tags = []

        source_specs = deepcopy(source.specs or {})
        specs_payload = payload.get("specs", source_specs)
        specs = normalize_specs(
            deepcopy(specs_payload or {}),
            wifi_tag_slugs=ProductWriteService._wifi_tag_slugs(selected_tags),
            strict_wifi_from_tags=False,
            title=title,
        )
        slug = await ProductWriteService._unique_slug(
            session,
            requested_slug=payload.get("slug") or f"{source.slug}-copy",
            title=title,
        )
        is_published = bool(payload.get("is_published", source.is_published))
        if make_unpublished:
            is_published = False

        product = Product(
            title=title,
            slug=slug,
            description=str(payload.get("description", source.description or "")),
            price=int(payload.get("price", source.price) or 0),
            old_price=payload.get("old_price", source.old_price),
            product_kind=ProductKindService.resolve(
                payload.get("product_kind"),
                specs=specs,
                fallback=source.product_kind,
            ),
            is_inverter=bool(payload.get("is_inverter", source.is_inverter)),
            power_cooling=payload.get("power_cooling", source.power_cooling),
            main_image=payload.get("main_image", source.main_image),
            images=list(source.images or []),
            tags=selected_tags,
            specs=specs,
            is_published=is_published,
            source_url=payload.get("source_url"),
            brand_id=payload.get("brand_id", source.brand_id),
            series_id=payload.get("series_id", source.series_id),
        )
        session.add(product)
        await session.flush()

        if copy_gallery:
            seen_urls: set[str] = set()
            for image in source.gallery_images or []:
                if not image.url or image.url in seen_urls:
                    continue
                seen_urls.add(image.url)
                session.add(
                    ProductImage(
                        product_id=product.id,
                        url=image.url,
                        is_installation_photo=image.is_installation_photo,
                    )
                )

        if manuals_payload is not None:
            manuals_to_save = manuals_payload
        elif copy_manuals:
            manuals_to_save = [
                {
                    "kind": item.kind,
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                }
                for item in (source.attachments or [])
                if item.kind == "manual"
            ]
        else:
            manuals_to_save = []
        await replace_manuals(
            session,
            product_id=product.id,
            manuals=manuals_to_save,
        )

        await sync_product_brand_series(
            session,
            product=product,
            specs=specs,
            title=title,
            tags=selected_tags,
            explicit_brand_id=payload.get("brand_id"),
            explicit_brand_override="brand_id" in payload,
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="product_duplicate",
            product_ids=[product.id],
            slugs=[product.slug],
        )
        await session.commit()
        return {"message": "Product duplicated", "id": product.id}

    @staticmethod
    async def save_main_image(
        session: AsyncSession,
        product_id: int,
        file_bytes: bytes,
        filename: str,
    ) -> Optional[dict]:
        from services.image_service import ImageService

        stmt = select(Product).where(Product.id == product_id)
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            return None

        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type="products",
            slug=product.slug,
            filename=filename,
        )
        product.main_image = ImageService.get_web_path(db_path)
        session.add(product)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="product_media",
            product_ids=[product.id],
            slugs=[product.slug],
        )
        await session.commit()
        return {"message": "Product updated", "id": product.id}

    @staticmethod
    async def update_product(
        session: AsyncSession,
        product_id: int,
        update_data: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = dict(update_data)
        manuals_payload = payload.pop("manuals", None)
        wifi_tag_slugs: Optional[List[str]] = None
        selected_tags: Optional[List[Tag]] = None
        if tag_ids is not None:
            tag_rows = (
                await session.execute(
                    select(Tag).where(Tag.id.in_(tag_ids)).options(selectinload(Tag.group))
                )
            ).scalars().all()
            selected_tags = list(tag_rows)
            wifi_tag_slugs = [tag.slug for tag in selected_tags if tag.slug in {"wifi-builtin", "wifi-ready"}]

        if "specs" in payload and payload["specs"] is not None:
            existing_product = None
            if wifi_tag_slugs is None:
                existing_product = await ProductDAO.get_by_id(session, product_id)
                wifi_tag_slugs = [
                    tag.slug
                    for tag in (existing_product.tags or [])
                    if tag.slug in {"wifi-builtin", "wifi-ready"}
                ] if existing_product else []
            if existing_product is None and "title" not in payload:
                existing_product = await ProductDAO.get_by_id(session, product_id)
            payload["specs"] = normalize_specs(
                payload["specs"],
                wifi_tag_slugs=wifi_tag_slugs,
                strict_wifi_from_tags=False,
                title=payload.get("title") or (existing_product.title if existing_product else ""),
            )

        previous_brand_slugs = await CatalogRevisionService.get_product_brand_slugs(
            session,
            [product_id],
        )
        product = await ProductDAO.update_full(session, product_id, payload, tag_ids, commit=False)
        if not product:
            return None
        if (
            product.product_kind == "unknown"
            and "specs" in payload
            and "product_kind" not in payload
        ):
            product.product_kind = ProductKindService.derive_from_specs(product.specs)
            session.add(product)
            await session.flush()

        if manuals_payload is not None:
            await replace_manuals(
                session,
                product_id=product_id,
                manuals=manuals_payload,
            )

        explicit_brand_override = "brand_id" in payload
        explicit_brand_id = payload.get("brand_id") if explicit_brand_override else None
        await sync_product_brand_series(
            session,
            product=product,
            specs=payload.get("specs", product.specs),
            title=payload.get("title", product.title),
            tags=selected_tags,
            explicit_brand_id=explicit_brand_id,
            explicit_brand_override=explicit_brand_override,
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="product_update",
            product_ids=[product.id],
            slugs=[product.slug],
            brand_slugs=previous_brand_slugs,
        )
        await session.commit()
        return {"message": "Product updated", "id": product.id}

    @staticmethod
    async def bulk_round_prices(session: AsyncSession, product_ids: List[int]) -> Dict[str, Any]:
        products = await ProductDAO.get_by_ids(session, product_ids)
        updated_count = 0
        updated_product_ids: List[int] = []
        updated_slugs: List[str] = []

        for product in products:
            new_price = (product.price // 50) * 50
            if new_price != product.price:
                product.price = new_price
                session.add(product)
                updated_count += 1
                if product.id is not None:
                    updated_product_ids.append(int(product.id))
                if product.slug:
                    updated_slugs.append(product.slug)

        if updated_count > 0:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="product_price_bulk_round",
                product_ids=updated_product_ids,
                slugs=updated_slugs,
            )
            await session.commit()

        return {"message": "Prices rounded", "updated_count": updated_count}

    @staticmethod
    async def bulk_set_prices_to_rrc(session: AsyncSession, product_ids: List[int]) -> Dict[str, Any]:
        products = await ProductDAO.get_by_ids(session, product_ids)
        metrics = await ProductSupplyMetricsService.compute_for_products(session, products)
        updated_count = 0
        skipped_count = 0
        updated_product_ids: List[int] = []
        updated_slugs: List[str] = []

        for product in products:
            recommended_price = metrics.get(product.id, {}).get("recommended_price_byn")
            if recommended_price is None:
                skipped_count += 1
                continue

            new_price = int(round(float(recommended_price)))
            if new_price <= 0:
                skipped_count += 1
                continue

            if product.price != new_price:
                product.price = new_price
                session.add(product)
                updated_count += 1
                if product.id is not None:
                    updated_product_ids.append(int(product.id))
                if product.slug:
                    updated_slugs.append(product.slug)

        if updated_count > 0:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="product_price_bulk_rrc",
                product_ids=updated_product_ids,
                slugs=updated_slugs,
            )
            await session.commit()

        processed_count = len(products)
        unchanged_count = processed_count - updated_count - skipped_count
        return {
            "message": "Prices set to RRC",
            "processed_count": processed_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count + unchanged_count,
        }

    @staticmethod
    async def add_gallery_images(
        session: AsyncSession,
        product_id: int,
        images_data: List[Dict[str, Any]],
    ) -> List[int]:
        from services.image_service import ImageService

        stmt = select(Product).where(Product.id == product_id)
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            return []

        created_ids = []
        for img_data in images_data:
            db_path = await ImageService.save_image(
                file_bytes=img_data["file_bytes"],
                entity_type="products",
                slug=product.slug,
                filename=img_data["filename"],
            )
            product_image = ProductImage(
                product_id=product_id,
                url=ImageService.get_web_path(db_path),
                is_installation_photo=img_data.get("is_installation_photo", False),
            )
            session.add(product_image)
            await session.flush()
            created_ids.append(product_image.id)

        if created_ids:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="product_gallery",
                product_ids=[product.id],
                slugs=[product.slug],
            )
            await session.commit()
        else:
            await session.commit()
        return created_ids

    @staticmethod
    async def bulk_update_tags(
        session: AsyncSession,
        product_ids: List[int],
        tag_ids: List[int],
        action: str,
    ) -> int:
        stmt = select(Product).where(Product.id.in_(product_ids)).options(selectinload(Product.tags))
        products = (await session.execute(stmt)).scalars().all()

        tag_stmt = select(Tag).where(Tag.id.in_(tag_ids))
        tags_to_apply = (await session.execute(tag_stmt)).scalars().all()

        for product in products:
            if action == "add":
                current_tag_ids = {tag.id for tag in product.tags}
                for tag in tags_to_apply:
                    if tag.id not in current_tag_ids:
                        product.tags.append(tag)
            elif action == "remove":
                product.tags = [tag for tag in product.tags if tag.id not in tag_ids]

        if products:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="product_tags",
                product_ids=[product.id for product in products if product.id is not None],
                slugs=[product.slug for product in products if product.slug],
            )
            await session.commit()
        else:
            await session.commit()
        return len(products)
