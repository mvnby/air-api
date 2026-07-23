"""
Repository Layer: Product Data Access Object (DAO).
Pure database operations. No business logic.
All methods accept AsyncSession as first argument for DI/transaction control.
"""
from typing import Optional, List, Dict, Any

from sqlalchemy import Integer, Float, Boolean, String, case, cast, func, and_, or_, exists
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Brand, Product, ProductImage, ProductSeries, FeatureSeriesLink, Tag, TagGroup, ProductTagLink
from models.product_constants import BTU_MAPPING
from models.supplier import ProductLocalStock, ProductSupplierMapping, SupplierOffer


ALLOWED_FILTER_GROUP_SLUGS = {"brand", "series", "expert-badge", "type", "category"}
ALLOWED_INDOOR_TYPE_FILTERS = {"duct", "cassette", "floor_ceiling", "column"}
BLACK_COLOR_PATTERNS = (
    "%черн%",
    "%чёрн%",
    "%Черн%",
    "%Чёрн%",
    "%ЧЕРН%",
    "%ЧЁРН%",
    "%black%",
)
CATALOG_CATEGORY_SLUGS = {"cat-household", "cat-multi", "cat-industrial"}
CATALOG_RANKING_WEIGHTS = {
    "availability": 100,
    "out_of_stock": -100,
    "manager_favorite": 80,
    "area_to_25": 50,
    "area_to_35": 30,
    "area_large": 10,
    "analytics_clicks": 0,
    "analytics_cart_adds": 0,
    "analytics_views": 0,
}


class ProductDAO:
    @staticmethod
    def _gallery_images_option(*, load_image_variants: bool = False):
        option = selectinload(Product.gallery_images)
        if load_image_variants:
            return option.selectinload(ProductImage.variants)
        return option

    @staticmethod
    def _series_option():
        return (
            selectinload(Product.series)
            .selectinload(ProductSeries.feature_links)
            .selectinload(FeatureSeriesLink.feature)
        )

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        product_id: int,
        *,
        is_published: Optional[bool] = None,
        load_image_variants: bool = False,
    ) -> Optional[Product]:
        stmt = select(Product).where(Product.id == product_id)
        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)
        stmt = stmt.options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(load_image_variants=load_image_variants),
            selectinload(Product.attachments),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(
        session: AsyncSession,
        slug: str,
        *,
        is_published: Optional[bool] = None,
        load_image_variants: bool = False,
    ) -> Optional[Product]:
        stmt = select(Product).where(Product.slug == slug)
        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)
        stmt = stmt.options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(load_image_variants=load_image_variants),
            selectinload(Product.attachments),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_published(
        session: AsyncSession,
        *,
        load_image_variants: bool = False,
    ) -> List[Product]:
        stmt = select(Product).where(Product.is_published == True).options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(load_image_variants=load_image_variants),
            selectinload(Product.attachments),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_published_by_series_id(
        session: AsyncSession,
        series_id: int,
        *,
        load_image_variants: bool = False,
    ) -> List[Product]:
        stmt = (
            select(Product)
            .where(
                Product.series_id == series_id,
                Product.is_published.is_(True),
            )
            .options(
                selectinload(Product.brand),
                ProductDAO._series_option(),
                selectinload(Product.tags).selectinload(Tag.group),
                ProductDAO._gallery_images_option(
                    load_image_variants=load_image_variants
                ),
                selectinload(Product.attachments),
            )
            .order_by(Product.title.asc(), Product.id.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def get_by_ids(
        session: AsyncSession,
        product_ids: List[int],
        *,
        load_image_variants: bool = False,
    ) -> List[Product]:
        if not product_ids:
            return []
        stmt = select(Product).where(Product.id.in_(product_ids)).options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(load_image_variants=load_image_variants),
            selectinload(Product.attachments),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _json_int_expr(session: AsyncSession, key: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return cast(func.json_extract(Product.specs, f"$.{key}"), Integer)
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key), Integer)

    @staticmethod
    def area_expr(session: AsyncSession):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return cast(func.json_extract(Product.specs, "$.area_m2"), Float)
        return cast(
            func.jsonb_extract_path_text(cast(Product.specs, JSONB), "area_m2"),
            Float,
        )

    @staticmethod
    def _json_bool_expr(session: AsyncSession, key: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return cast(func.json_extract(Product.specs, f"$.{key}"), Integer)
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key), Boolean)

    @staticmethod
    def _json_text_expr(session: AsyncSession, key: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return func.lower(cast(func.json_extract(Product.specs, f"$.{key}"), String))
        return func.lower(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key))

    @staticmethod
    def _json_path_int_expr(session: AsyncSession, *path: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            json_path = "$." + ".".join(path)
            return cast(func.json_extract(Product.specs, json_path), Integer)
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), *path), Integer)

    @staticmethod
    def _json_path_text_expr(session: AsyncSession, *path: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            json_path = "$." + ".".join(path)
            return func.lower(cast(func.json_extract(Product.specs, json_path), String))
        return func.lower(func.jsonb_extract_path_text(cast(Product.specs, JSONB), *path))

    @staticmethod
    def _apply_common_filters(
        session: AsyncSession,
        stmt,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[List[str]] = None,
        tag_slugs: Optional[List[str]] = None,
        brand_slugs: Optional[List[str]] = None,
        series_id: Optional[int] = None,
        is_published: Optional[bool] = True,
    ):
        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)

        area_expr = ProductDAO.area_expr(session)
        if area_min is not None:
            stmt = stmt.where(area_expr >= area_min)
        if area_max is not None:
            stmt = stmt.where(area_expr <= area_max)

        if min_price is not None:
            stmt = stmt.where(Product.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)

        if is_inverter is not None:
            stmt = stmt.where(Product.is_inverter == is_inverter)

        if heating_min is not None:
            typed_heat_min_expr = ProductDAO._json_path_int_expr(
                session,
                "__typed_specs",
                "temp_range_heat",
                "min",
            )
            legacy_heat_min_expr = ProductDAO._json_int_expr(session, "__filter_min_heat")
            stmt = stmt.where(func.coalesce(typed_heat_min_expr, legacy_heat_min_expr) <= heating_min)

        if has_wifi is not None:
            wifi_expr = ProductDAO._json_bool_expr(session, "__filter_wifi")
            wifi_state_expr = ProductDAO._json_path_text_expr(
                session,
                "__typed_specs",
                "wifi_state",
                "value",
            )
            legacy_wifi_tag_subq = (
                select(ProductTagLink.product_id)
                .join(Tag, ProductTagLink.tag_id == Tag.id)
                .where(Tag.slug == "wifi-builtin")
            )
            if session.bind is not None and session.bind.dialect.name == "sqlite":
                if has_wifi:
                    stmt = stmt.where(
                        or_(
                            wifi_state_expr.in_(("builtin", "ready")),
                            and_(wifi_state_expr.is_(None), wifi_expr == 1),
                            Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
                else:
                    stmt = stmt.where(
                        and_(
                            or_(
                                wifi_state_expr == "none",
                                and_(wifi_state_expr.is_(None), wifi_expr == 0),
                            ),
                            ~Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
            else:
                if has_wifi:
                    stmt = stmt.where(
                        or_(
                            wifi_state_expr.in_(("builtin", "ready")),
                            and_(wifi_state_expr.is_(None), wifi_expr == True),
                            Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
                else:
                    stmt = stmt.where(
                        and_(
                            or_(
                                wifi_state_expr == "none",
                                and_(wifi_state_expr.is_(None), wifi_expr == False),
                            ),
                            ~Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )

        if has_fresh_air is not None:
            fresh_air_expr = ProductDAO._json_bool_expr(session, "fresh_air")
            if has_fresh_air:
                if session.bind is not None and session.bind.dialect.name == "sqlite":
                    stmt = stmt.where(fresh_air_expr == 1)
                else:
                    stmt = stmt.where(fresh_air_expr == True)
            else:
                if session.bind is not None and session.bind.dialect.name == "sqlite":
                    stmt = stmt.where(or_(fresh_air_expr == 0, fresh_air_expr.is_(None)))
                else:
                    stmt = stmt.where(or_(fresh_air_expr == False, fresh_air_expr.is_(None)))

        if color == "black":
            color_expr = ProductDAO._json_text_expr(session, "color")
            stmt = stmt.where(or_(*(color_expr.ilike(pattern) for pattern in BLACK_COLOR_PATTERNS)))

        if indoor_types:
            normalized_types = [
                str(value).strip().lower()
                for value in indoor_types
                if value and str(value).strip().lower() in ALLOWED_INDOOR_TYPE_FILTERS
            ]
            if normalized_types:
                typed_indoor_type_expr = ProductDAO._json_path_text_expr(
                    session,
                    "__typed_specs",
                    "indoor_type",
                    "value",
                )
                legacy_indoor_type_expr = ProductDAO._json_text_expr(session, "__filter_indoor_type")
                stmt = stmt.where(func.coalesce(typed_indoor_type_expr, legacy_indoor_type_expr).in_(normalized_types))

        if tag_slugs:
            normalized_slugs = [slug.strip().lower() for slug in tag_slugs if slug and slug.strip()]
            # AND between groups, OR within each group.
            for group_slug in sorted(ALLOWED_FILTER_GROUP_SLUGS):
                group_subq = (
                    select(ProductTagLink.product_id)
                    .join(Tag, ProductTagLink.tag_id == Tag.id)
                    .join(TagGroup, Tag.group_id == TagGroup.id)
                    .where(Tag.slug.in_(normalized_slugs))
                    .where(TagGroup.slug == group_slug)
                )
                group_slug_exists = (
                    select(Tag.id)
                    .join(TagGroup, Tag.group_id == TagGroup.id)
                    .where(Tag.slug.in_(normalized_slugs))
                    .where(TagGroup.slug == group_slug)
                )
                # Backcompat: unknown/legacy slugs should be ignored (not zero-result).
                stmt = stmt.where(or_(~exists(group_slug_exists), Product.id.in_(group_subq)))

        if brand_slugs:
            normalized_brand_slugs = [
                slug.strip().lower()
                for slug in brand_slugs
                if slug and slug.strip()
            ]
            if normalized_brand_slugs:
                brand_subq = select(Brand.id).where(Brand.slug.in_(normalized_brand_slugs))
                stmt = stmt.where(Product.brand_id.in_(brand_subq))

        if series_id is not None:
            stmt = stmt.where(Product.series_id == series_id)

        return stmt

    @staticmethod
    def _apply_faceted_filters(stmt, faceted_tag_ids: Optional[dict[int, list[int]]] = None):
        if faceted_tag_ids:
            for _, tag_ids in faceted_tag_ids.items():
                if not tag_ids:
                    continue
                subq = select(ProductTagLink.product_id).where(ProductTagLink.tag_id.in_(tag_ids))
                stmt = stmt.where(Product.id.in_(subq))
        return stmt

    @staticmethod
    def _apply_category_status_filter(stmt, category_status: Optional[str] = None):
        normalized_status = (category_status or "").strip().lower()
        if normalized_status != "missing":
            return stmt

        category_subq = (
            select(ProductTagLink.product_id)
            .join(Tag, ProductTagLink.tag_id == Tag.id)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(ProductTagLink.product_id == Product.id)
            .where(TagGroup.slug == "category")
            .where(Tag.slug.in_(CATALOG_CATEGORY_SLUGS))
        )
        return stmt.where(~exists(category_subq))

    @staticmethod
    def _apply_smart_search_filter(session: AsyncSession, stmt, query: str):
        if not query:
            return stmt

        tokens = query.strip().split()
        text_tokens = [t for t in tokens if not t.isdigit()]
        number_tokens = [t for t in tokens if t.isdigit()]

        for word in text_tokens:
            word_filter = or_(
                Product.title.ilike(f"%{word}%"),
                Product.tags.any(Tag.title.ilike(f"%{word}%")),
            )
            stmt = stmt.where(word_filter)

        for num in number_tokens:
            if num in BTU_MAPPING:
                ranges = BTU_MAPPING[num]
                num_filter = or_(
                    ProductDAO.area_expr(session).between(ranges["area"][0], ranges["area"][1]),
                    Product.power_cooling.between(ranges["power"][0], ranges["power"][1]),
                    Product.title.ilike(f"%{num}%"),
                )
            else:
                # Non-standard number (e.g. "2024") → plain text search
                num_filter = Product.title.ilike(f"%{num}%")
            stmt = stmt.where(num_filter)
        
        return stmt

    @staticmethod
    def _catalog_recommendation_score_expr(
        session: AsyncSession,
        area_max: Optional[int] = None,
    ):
        favorite_tag_exists = exists(
            select(ProductTagLink.product_id)
            .join(Tag, ProductTagLink.tag_id == Tag.id)
            .where(
                ProductTagLink.product_id == Product.id,
                Tag.slug == "manager-favorite",
            )
        )
        local_stock_exists = exists(
            select(ProductLocalStock.id).where(
                ProductLocalStock.product_id == Product.id,
                ProductLocalStock.qty > 0,
            )
        )
        supplier_stock_exists = exists(
            select(ProductSupplierMapping.id)
            .join(
                SupplierOffer,
                and_(
                    ProductSupplierMapping.supplier_id == SupplierOffer.supplier_id,
                    ProductSupplierMapping.external_id == SupplierOffer.external_id,
                ),
            )
            .where(
                ProductSupplierMapping.product_id == Product.id,
                ProductSupplierMapping.is_active.is_(True),
                SupplierOffer.is_active.is_(True),
                SupplierOffer.qty > 0,
            )
        )

        availability_score = case(
            (
                or_(local_stock_exists, supplier_stock_exists),
                CATALOG_RANKING_WEIGHTS["availability"],
            ),
            else_=CATALOG_RANKING_WEIGHTS["out_of_stock"],
        )
        favorite_score = case(
            (favorite_tag_exists, CATALOG_RANKING_WEIGHTS["manager_favorite"]),
            else_=0,
        )
        area = ProductDAO.area_expr(session)
        area_threshold = int(area_max) if area_max else None
        if area_threshold and area_threshold > 35:
            if area_threshold <= 50:
                area_score = case(
                    (
                        and_(area > 35, area <= area_threshold),
                        CATALOG_RANKING_WEIGHTS["area_to_25"],
                    ),
                    (
                        and_(area > 25, area <= 35),
                        CATALOG_RANKING_WEIGHTS["area_to_35"],
                    ),
                    (area <= 25, CATALOG_RANKING_WEIGHTS["area_large"]),
                    else_=0,
                )
            elif area_threshold <= 70:
                area_score = case(
                    (
                        and_(area > 50, area <= area_threshold),
                        CATALOG_RANKING_WEIGHTS["area_to_25"],
                    ),
                    (
                        and_(area > 35, area <= 50),
                        CATALOG_RANKING_WEIGHTS["area_to_35"],
                    ),
                    (
                        and_(area > 25, area <= 35),
                        CATALOG_RANKING_WEIGHTS["area_large"],
                    ),
                    (area <= 25, 5),
                    else_=0,
                )
            else:
                area_score = case(
                    (
                        and_(area > 70, area <= area_threshold),
                        CATALOG_RANKING_WEIGHTS["area_to_25"],
                    ),
                    (
                        and_(area > 50, area <= 70),
                        CATALOG_RANKING_WEIGHTS["area_to_35"],
                    ),
                    (area <= 50, CATALOG_RANKING_WEIGHTS["area_large"]),
                    else_=0,
                )
        elif area_threshold and area_threshold > 25:
            area_score = case(
                (
                    and_(area > 25, area <= area_threshold),
                    CATALOG_RANKING_WEIGHTS["area_to_25"],
                ),
                (area <= 25, CATALOG_RANKING_WEIGHTS["area_to_35"]),
                else_=0,
            )
        else:
            area_score = case(
                (area <= 25, CATALOG_RANKING_WEIGHTS["area_to_25"]),
                (area <= 35, CATALOG_RANKING_WEIGHTS["area_to_35"]),
                (area > 35, CATALOG_RANKING_WEIGHTS["area_large"]),
                else_=0,
            )

        return availability_score + favorite_score + area_score

    @staticmethod
    def _catalog_brand_priority_expr():
        brand_sort_order = (
            select(Brand.sort_order)
            .where(Brand.id == Product.brand_id)
            .scalar_subquery()
        )
        return func.coalesce(brand_sort_order, 999)

    @staticmethod
    async def get_filtered(
        session: AsyncSession,
        *,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[List[str]] = None,
        tag_slugs: Optional[List[str]] = None,
        brand_slugs: Optional[List[str]] = None,
        brand_ids: Optional[List[int]] = None,
        series_ids: Optional[List[int]] = None,
        product_kinds: Optional[List[str]] = None,
        is_published: Optional[bool] = True,
        sort: str = "recommended",
        page: int = 1,
        limit: int = 20,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
        load_image_variants: bool = False,
    ) -> List[Product]:
        stmt = select(Product).options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(load_image_variants=load_image_variants),
            selectinload(Product.attachments),
        )

        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            tag_slugs=tag_slugs,
            brand_slugs=brand_slugs,
            is_published=is_published,
        )
        if brand_ids:
            stmt = stmt.where(Product.brand_id.in_(brand_ids))
        if series_ids:
            stmt = stmt.where(Product.series_id.in_(series_ids))
        if product_kinds:
            stmt = stmt.where(Product.product_kind.in_(product_kinds))
        if search_query:
            stmt = ProductDAO._apply_smart_search_filter(session, stmt, search_query)
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)

        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(Product.price.desc())
        elif sort == "area_asc":
            stmt = stmt.order_by(ProductDAO.area_expr(session).asc())
        elif sort == "area_desc":
            stmt = stmt.order_by(ProductDAO.area_expr(session).desc())
        elif sort == "newest":
            stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
        else:
            stmt = stmt.order_by(
                ProductDAO._catalog_recommendation_score_expr(session, area_max=area_max).desc(),
                ProductDAO._catalog_brand_priority_expr().asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_filtered(
        session: AsyncSession,
        *,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[List[str]] = None,
        tag_slugs: Optional[List[str]] = None,
        brand_slugs: Optional[List[str]] = None,
        is_published: Optional[bool] = True,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(Product.id))
        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            tag_slugs=tag_slugs,
            brand_slugs=brand_slugs,
            is_published=is_published,
        )
        if search_query:
            stmt = ProductDAO._apply_smart_search_filter(session, stmt, search_query)
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def update_price(
        session: AsyncSession,
        product_id: int,
        new_price: int,
        commit: bool = True,
    ) -> bool:
        product = await session.get(Product, product_id)
        if not product:
            return False
        product.price = new_price
        session.add(product)
        if commit:
            await session.commit()
        else:
            await session.flush()
        return True

    @staticmethod
    async def delete(session: AsyncSession, product_id: int) -> bool:
        product = await session.get(Product, product_id)
        if not product:
            return False
        await session.delete(product)
        await session.commit()
        return True

    @staticmethod
    async def update_full(
        session: AsyncSession,
        product_id: int,
        update_data: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
        commit: bool = True,
    ) -> Optional[Product]:
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            return None

        for key, value in update_data.items():
            setattr(product, key, value)

        if tag_ids is not None:
            tag_stmt = select(Tag).where(Tag.id.in_(tag_ids)).options(selectinload(Tag.group))
            tag_result = await session.execute(tag_stmt)
            product.tags = list(tag_result.scalars().all())

        session.add(product)
        if commit:
            await session.commit()
            await session.refresh(product)
        else:
            await session.flush()
        return product

    @staticmethod
    async def get_for_manager(
        session: AsyncSession,
        page: int = 1,
        limit: int = 40,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        brand_slugs: Optional[List[str]] = None,
        series_id: Optional[int] = None,
        category_slug: Optional[str] = None,
        category_status: Optional[str] = None,
        sort: str = "recommended",
    ) -> tuple[List[Product], int]:
        normalized_category_status = (category_status or "").strip().lower()
        stmt = select(Product).options(
            ProductDAO._gallery_images_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.attachments),
        )
        count_stmt = select(func.count(Product.id))

        common_filter_kwargs = {
            "area_min": area_min,
            "area_max": area_max,
            "heating_min": heating_min,
            "has_wifi": has_wifi,
            "has_fresh_air": has_fresh_air,
            "is_inverter": is_inverter,
            "tag_slugs": [category_slug] if category_slug and normalized_category_status != "missing" else None,
            "brand_slugs": brand_slugs,
            "series_id": series_id,
            "is_published": is_published,
        }
        stmt = ProductDAO._apply_common_filters(
            session=session,
            stmt=stmt,
            **common_filter_kwargs,
        )
        stmt = ProductDAO._apply_category_status_filter(stmt, normalized_category_status)
        count_stmt = ProductDAO._apply_common_filters(
            session=session,
            stmt=count_stmt,
            **common_filter_kwargs,
        )
        count_stmt = ProductDAO._apply_category_status_filter(count_stmt, normalized_category_status)

        if search:
            stmt = stmt.where(Product.title.ilike(f"%{search}%"))
            count_stmt = count_stmt.where(Product.title.ilike(f"%{search}%"))

        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(Product.price.desc())
        elif sort == "title":
            stmt = stmt.order_by(Product.title.asc())
        elif sort == "newest":
            stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
        elif sort == "recommended":
            stmt = stmt.order_by(
                ProductDAO._catalog_recommendation_score_expr(session, area_max=area_max).desc(),
                ProductDAO._catalog_brand_priority_expr().asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )
        else:
            stmt = stmt.order_by(Product.id.desc())

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)

        total = (await session.execute(count_stmt)).scalar() or 0
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_for_generation(session: AsyncSession, product_id: int) -> Optional[Product]:
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()
