"""
Service Layer: Product business logic.
"""
from typing import Optional, List, Dict, Any
import ast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select, func
from thefuzz import process

from crud.product import ProductDAO
from models import Product, Tag, TagGroup, ProductTagLink
from services.spec_normalizer import normalize_specs


ALLOWED_FILTER_GROUP_SLUGS = {"brand", "series", "expert-badge"}

# Транслитерация RU → EN для поиска
TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ы": "y", "э": "e", "ю": "yu", "я": "ya", "ь": "", "ъ": "",
}


def transliterate(text: str) -> str:
    result = []
    for char in text.lower():
        result.append(TRANSLIT_MAP.get(char, char))
    return "".join(result)


def _sanitize_specs(specs: Any) -> Dict[str, Any]:
    value = specs
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            value = {}
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if not str(k).startswith("__")}


class ProductService:
    @staticmethod
    async def search(
        session: AsyncSession,
        query: Optional[str] = None,
        is_inverter: Optional[bool] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        products = await ProductDAO.get_filtered(
            session,
            is_inverter=is_inverter,
            is_published=True,
            limit=max(limit, 1),
        )

        if query:
            query_lower = query.lower()
            choices = {p.id: p.title.lower() for p in products}
            matches = process.extract(query_lower, choices, limit=limit)
            matched_ids = [m[2] for m in matches if m[1] >= 60]

            if len(matched_ids) < 2:
                translit_query = transliterate(query)
                if translit_query != query_lower:
                    translit_matches = process.extract(translit_query, choices, limit=limit)
                    for match in translit_matches:
                        if match[1] >= 60 and match[2] not in matched_ids:
                            matched_ids.append(match[2])

            id_map = {p.id: p for p in products}
            products = [id_map[pid] for pid in matched_ids if pid in id_map]

        return [ProductService._to_dict(p) for p in products[:limit]]

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        area: int,
        is_inverter: bool,
        tag_slugs: Optional[List[str]] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        faceted_tag_ids = None
        if tag_slugs:
            faceted_tag_ids = await ProductService.resolve_slugs_to_grouped_ids(session, tag_slugs)

        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            min_price=min_price,
            max_price=max_price,
            is_published=True,
            faceted_tag_ids=faceted_tag_ids,
            sort="area_asc",
            limit=limit,
        )
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Dict[str, Any]]:
        product = await ProductDAO.get_by_id(session, product_id)
        if product:
            return ProductService._to_dict(product)
        return None

    @staticmethod
    async def get_product_by_identifier(session: AsyncSession, identifier: str) -> Optional[Product]:
        if identifier.isdigit():
            product = await ProductDAO.get_by_id(session, int(identifier))
            if product:
                return product
        return await ProductDAO.get_by_slug(session, identifier)

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Dict[str, Any]]:
        products = await ProductDAO.get_all_published(session)
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_area(session: AsyncSession, area: int, range_offset: int = 10) -> List[Dict[str, Any]]:
        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            area_max=area + range_offset,
            is_published=True,
        )
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    async def resolve_slugs_to_grouped_ids(
        session: AsyncSession,
        slugs: List[str],
    ) -> Dict[int, List[int]]:
        if not slugs:
            return {}

        stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.slug.in_(slugs))
            .where(TagGroup.slug.in_(ALLOWED_FILTER_GROUP_SLUGS))
        )
        tags = (await session.execute(stmt)).scalars().all()

        grouped: Dict[int, List[int]] = {}
        for tag in tags:
            if tag.group_id is None:
                continue
            grouped.setdefault(tag.group_id, []).append(tag.id)
        return grouped

    @staticmethod
    async def get_series_siblings(
        session: AsyncSession,
        product: Product,
        limit: int = 8,
    ) -> List[Product]:
        series_tag_ids = [
            tag.id
            for tag in (product.tags or [])
            if tag.group and tag.group.slug == "series"
        ]
        if not series_tag_ids:
            return []

        brand_tag_ids = {
            tag.id for tag in (product.tags or [])
            if tag.group and tag.group.slug == "brand"
        }

        series_product_ids = (
            select(ProductTagLink.product_id)
            .where(ProductTagLink.tag_id.in_(series_tag_ids))
            .distinct()
            .subquery()
        )

        stmt = (
            select(Product)
            .join(series_product_ids, Product.id == series_product_ids.c.product_id)
            .where(Product.id != product.id)
            .where(Product.is_published == True)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        candidates = list((await session.execute(stmt)).scalars().all())

        def score(item: Product) -> tuple[int, int]:
            item_brand_ids = {
                tag.id for tag in (item.tags or [])
                if tag.group and tag.group.slug == "brand"
            }
            same_brand = 0 if (brand_tag_ids and item_brand_ids.intersection(brand_tag_ids)) else 1
            return (same_brand, item.price or 0)

        candidates.sort(key=score)
        return candidates[:limit]

    @staticmethod
    async def get_filters_config(session: AsyncSession) -> Dict[str, Any]:
        price_q = await session.execute(
            select(func.min(Product.price), func.max(Product.price)).where(Product.is_published == True)
        )
        area_q = await session.execute(
            select(func.min(Product.area), func.max(Product.area)).where(Product.is_published == True)
        )
        price_min, price_max = price_q.one()
        area_min, area_max = area_q.one()

        brands_stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.is_public == True)
            .where(TagGroup.slug == "brand")
            .order_by(Tag.sort_order, Tag.title)
        )
        expert_stmt = (
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(Tag.is_public == True)
            .where(
                (TagGroup.slug == "expert-badge") | (TagGroup.is_expert_badge == True)
            )
            .order_by(Tag.sort_order, Tag.title)
        )

        brands = list((await session.execute(brands_stmt)).scalars().all())
        expert_tags = list((await session.execute(expert_stmt)).scalars().all())

        return {
            "price": {"min": price_min, "max": price_max},
            "area": {"min": area_min, "max": area_max},
            "brands": [{"id": t.id, "title": t.title, "slug": t.slug} for t in brands],
            "expert_tags": [{"id": t.id, "title": t.title, "slug": t.slug} for t in expert_tags],
        }

    @staticmethod
    def _to_dict(product: Product) -> Dict[str, Any]:
        data = product.model_dump()
        data["categories"] = [t.title for t in product.tags]

        tags_data = []
        for tag in product.tags:
            tag_dict = tag.model_dump()
            if tag.group:
                tag_dict["group"] = tag.group.model_dump()
            tags_data.append(tag_dict)
        data["tags"] = tags_data

        if data.get("main_image") and not data["main_image"].startswith("/"):
            data["main_image"] = "/" + data["main_image"]

        gallery = sorted(
            product.gallery_images,
            key=lambda item: (item.is_installation_photo, item.id),
        )

        def to_web_path(path: str) -> str:
            if path and not path.startswith("/"):
                return f"/{path}"
            return path

        data["images"] = [to_web_path(img.url) for img in gallery]
        data["gallery_images"] = [
            {
                **img.model_dump(),
                "url": to_web_path(img.url),
            }
            for img in gallery
        ]
        data["specs"] = _sanitize_specs(data.get("specs"))
        return data

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
                    "specs": _sanitize_specs(p.specs),
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
            tag_rows = (
                await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
            ).scalars().all()
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
        from models import ProductImage

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
