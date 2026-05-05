"""Write-oriented product service operations (mutations/updates)."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models import Product, ProductImage, Tag
from services.brand_series_service import sync_product_brand_series
from services.product_attachment_service import replace_manuals
from services.spec_normalizer import normalize_specs
from services.product_supply_metrics_service import ProductSupplyMetricsService


class ProductWriteService:
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

        product = await ProductDAO.update_full(session, product_id, payload, tag_ids)
        if not product:
            return None

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
        await session.commit()
        return {"message": "Product updated", "id": product.id}

    @staticmethod
    async def bulk_round_prices(session: AsyncSession, product_ids: List[int]) -> Dict[str, Any]:
        products = await ProductDAO.get_by_ids(session, product_ids)
        updated_count = 0

        for product in products:
            new_price = (product.price // 50) * 50
            if new_price != product.price:
                product.price = new_price
                session.add(product)
                updated_count += 1

        if updated_count > 0:
            await session.commit()

        return {"message": "Prices rounded", "updated_count": updated_count}

    @staticmethod
    async def bulk_set_prices_to_rrc(session: AsyncSession, product_ids: List[int]) -> Dict[str, Any]:
        products = await ProductDAO.get_by_ids(session, product_ids)
        metrics = await ProductSupplyMetricsService.compute_for_products(session, products)
        updated_count = 0
        skipped_count = 0

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

        if updated_count > 0:
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

        await session.commit()
        return len(products)
