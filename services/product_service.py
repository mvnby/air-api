"""Compatibility facade for product service operations.

Read/filter methods are inherited from ProductReadService.
Write/mutation methods remain here while decomposition is in progress.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models import Product, ProductImage, Tag
from services.product_read_service import ProductReadService
from services.spec_normalizer import normalize_specs
from services.product_serialization import sanitize_specs


class ProductService(ProductReadService):
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
    async def get_manager_list(
        session: AsyncSession,
        page: int = 1,
        limit: int = 40,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        sort: str = "newest",
    ) -> Dict[str, Any]:
        items, total = await ProductDAO.get_for_manager(
            session, page, limit, search, is_published, area_min, area_max, is_inverter, sort
        )

        formatted_items = []
        for p in items:
            formatted_items.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "slug": p.slug,
                    "price": p.price,
                    "old_price": p.old_price,
                    "area": p.area,
                    "is_inverter": p.is_inverter,
                    "power_cooling": p.power_cooling,
                    "main_image": p.main_image,
                    "is_published": p.is_published,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "specs": sanitize_specs(p.specs),
                    "gallery_images": [
                        {
                            "id": img.id,
                            "url": img.url,
                            "is_installation_photo": img.is_installation_photo,
                        }
                        for img in (p.gallery_images or [])
                    ],
                    "tags": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "slug": t.slug,
                            "group_title": t.group.title if t.group else None,
                            "group_color": t.group.color if t.group else "secondary",
                        }
                        for t in (p.tags or [])
                    ],
                }
            )

        return {
            "items": formatted_items,
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def update_product(
        session: AsyncSession,
        product_id: int,
        update_data: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = dict(update_data)
        wifi_tag_slugs: Optional[List[str]] = None
        if tag_ids is not None:
            tag_rows = (await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))).scalars().all()
            wifi_tag_slugs = [tag.slug for tag in tag_rows if tag.slug in {"wifi-builtin", "wifi-ready"}]

        if "specs" in payload and payload["specs"] is not None:
            if wifi_tag_slugs is None:
                existing_product = await ProductDAO.get_by_id(session, product_id)
                wifi_tag_slugs = [
                    tag.slug
                    for tag in (existing_product.tags or [])
                    if tag.slug in {"wifi-builtin", "wifi-ready"}
                ] if existing_product else []
            payload["specs"] = normalize_specs(
                payload["specs"],
                wifi_tag_slugs=wifi_tag_slugs,
                strict_wifi_from_tags=True,
            )

        product = await ProductDAO.update_full(session, product_id, payload, tag_ids)
        if not product:
            return None
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
    async def get_all_tags(session: AsyncSession) -> List[Dict[str, Any]]:
        from crud.tag import TagDAO

        groups = await TagDAO.get_all_grouped(session)
        return [
            {
                "id": g.id,
                "title": g.title,
                "slug": g.slug,
                "color": g.color,
                "allow_multiple": g.allow_multiple,
                "tags": [
                    {"id": t.id, "title": t.title, "slug": t.slug}
                    for t in sorted(g.tags, key=lambda item: (item.sort_order, item.title))
                ],
            }
            for g in groups
        ]

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
