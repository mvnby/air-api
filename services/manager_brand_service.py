from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureSeriesLink,
    Product,
    ProductSeries,
    ProductTagLink,
    Tag,
    TagGroup,
)
from services.brand_series_service import extract_series_name, sync_product_brand_series
from services.catalog_revision_service import CatalogRevisionService
from services.feature_scope_policy import FeatureScopePolicy


class ManagerBrandService:
    @staticmethod
    async def list_brands(session: AsyncSession) -> List[Dict[str, Any]]:
        rows = (
            await session.execute(
                select(Brand, func.count(Product.id).label("products_count"))
                .outerjoin(Product, Product.brand_id == Brand.id)
                .group_by(Brand.id)
                .order_by(Brand.sort_order.asc(), Brand.title.asc())
            )
        ).all()

        return [
            ManagerBrandService._serialize_brand(brand, products_count=int(products_count or 0))
            for brand, products_count in rows
        ]

    @staticmethod
    async def list_brand_features(
        session: AsyncSession,
        brand_id: int,
    ) -> List[Dict[str, Any]]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        rows = (
            await session.execute(
                select(Feature, func.count(FeatureSeriesLink.id).label("series_count"))
                .outerjoin(FeatureSeriesLink, FeatureSeriesLink.feature_id == Feature.id)
                .where(Feature.brand_id == brand_id)
                .where(Feature.is_active.is_(True))
                .group_by(Feature.id)
                .order_by(Feature.sort_order.asc(), Feature.name.asc())
            )
        ).all()
        return [
            ManagerBrandService._serialize_brand_feature(feature, series_count=int(series_count or 0))
            for feature, series_count in rows
        ]

    @staticmethod
    async def create_brand_feature(
        session: AsyncSession,
        brand_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Название фичи не может быть пустым.")

        slug = ManagerBrandService._build_feature_slug(payload.get("slug"), title)
        await ManagerBrandService._ensure_brand_feature_slug_available(session, brand_id=brand_id, slug=slug)

        category_id = (
            await session.execute(
                select(FeatureCategory.id).where(FeatureCategory.slug == "comfort")
            )
        ).scalar_one_or_none()
        if category_id is None:
            category = FeatureCategory(slug="comfort", name="Комфорт", sort_order=10)
            session.add(category)
            await session.flush()
            category_id = int(category.id)
        feature = Feature(
            brand_id=brand_id,
            category_id=category_id,
            scope_type="brand",
            name=title,
            slug=slug,
            full_description=ManagerBrandService._clean_optional_text(payload.get("text")),
            image_url=ManagerBrandService._clean_optional_text(payload.get("image_url")),
            icon=ManagerBrandService._clean_optional_text(payload.get("icon")),
            footnote=ManagerBrandService._clean_optional_text(payload.get("footnote")),
            source_url=ManagerBrandService._clean_optional_text(payload.get("source_url")),
            aliases=ManagerBrandService._normalize_string_list(payload.get("aliases")),
            is_active=bool(payload.get("is_published", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        session.add(feature)
        await session.flush()
        session.add(
            FeatureBrandLink(
                brand_id=brand_id,
                feature_id=int(feature.id),
                source="manual",
                sort_order=feature.sort_order,
            )
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_feature_create",
            brand_slugs=[brand.slug],
        )
        await session.commit()
        await session.refresh(feature)
        return ManagerBrandService._serialize_brand_feature(feature, series_count=0)

    @staticmethod
    async def update_brand_feature(
        session: AsyncSession,
        brand_id: int,
        feature_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        feature = await ManagerBrandService._get_brand_feature(session, brand_id, feature_id)
        if "title" in payload and payload["title"] is not None:
            title = str(payload["title"]).strip()
            if not title:
                raise HTTPException(status_code=400, detail="Название фичи не может быть пустым.")
            feature.name = title
        if "slug" in payload and payload["slug"] is not None:
            slug = ManagerBrandService._build_feature_slug(payload["slug"], feature.name)
            if slug != feature.slug:
                await ManagerBrandService._ensure_brand_feature_slug_available(
                    session,
                    brand_id=brand_id,
                    slug=slug,
                    exclude_feature_id=feature_id,
                )
                feature.slug = slug
        if "text" in payload:
            feature.full_description = ManagerBrandService._clean_optional_text(payload["text"])
        if "image_url" in payload:
            feature.image_url = ManagerBrandService._clean_optional_text(payload["image_url"])
        if "icon" in payload:
            feature.icon = ManagerBrandService._clean_optional_text(payload["icon"])
        if "footnote" in payload:
            feature.footnote = ManagerBrandService._clean_optional_text(payload["footnote"])
        if "source_url" in payload:
            feature.source_url = ManagerBrandService._clean_optional_text(payload["source_url"])
        if "aliases" in payload and payload["aliases"] is not None:
            feature.aliases = ManagerBrandService._normalize_string_list(payload["aliases"])
        if "is_published" in payload and payload["is_published"] is not None:
            feature.is_active = bool(payload["is_published"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            feature.sort_order = int(payload["sort_order"])

        session.add(feature)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_feature_update",
            brand_slugs=[brand.slug],
        )
        await session.commit()
        await session.refresh(feature)
        series_count = await ManagerBrandService._brand_feature_series_count(session, feature_id)
        return ManagerBrandService._serialize_brand_feature(feature, series_count=series_count)

    @staticmethod
    async def delete_brand_feature(
        session: AsyncSession,
        brand_id: int,
        feature_id: int,
    ) -> None:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        feature = await ManagerBrandService._get_brand_feature(session, brand_id, feature_id)
        series_count = await ManagerBrandService._brand_feature_series_count(session, feature_id)
        if series_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить фичу: она привязана к сериям бренда.",
            )
        feature.is_active = False
        feature.archived_at = datetime.now()
        session.add(feature)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_feature_delete",
            brand_slugs=[brand.slug],
        )
        await session.commit()

    @staticmethod
    async def create_brand(
        session: AsyncSession,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Название бренда не может быть пустым.")

        requested_slug = str(payload.get("slug") or "").strip()
        slug = requested_slug or slugify(title, lowercase=True)
        if not slug:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug бренда.")

        existing_brand = (
            await session.execute(select(Brand).where(Brand.slug == slug))
        ).scalar_one_or_none()
        if existing_brand is not None:
            raise HTTPException(status_code=400, detail=f"Бренд со slug '{slug}' уже существует.")

        brand = Brand(
            title=title,
            slug=slug,
            logo_url=payload.get("logo_url"),
            description=payload.get("description"),
            is_published=bool(payload.get("is_published", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        session.add(brand)
        await session.flush()

        await ManagerBrandService._sync_brand_tag(session, brand=brand, previous_slug=None)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_create",
            brand_slugs=[brand.slug],
        )
        await session.commit()
        await session.refresh(brand)
        return ManagerBrandService._serialize_brand(brand, products_count=0)

    @staticmethod
    async def update_brand(
        session: AsyncSession,
        brand_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        previous_slug = brand.slug

        if "title" in payload and payload["title"] is not None:
            title = str(payload["title"]).strip()
            if not title:
                raise HTTPException(status_code=400, detail="Название бренда не может быть пустым.")
            brand.title = title

        if "slug" in payload and payload["slug"] is not None:
            requested_slug = str(payload["slug"]).strip()
            new_slug = requested_slug or slugify(brand.title, lowercase=True)
            if not new_slug:
                raise HTTPException(status_code=400, detail="Не удалось сформировать slug бренда.")

            if new_slug != brand.slug:
                existing_brand = (
                    await session.execute(
                        select(Brand).where(Brand.slug == new_slug, Brand.id != brand_id)
                    )
                ).scalar_one_or_none()
                if existing_brand is not None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Бренд со slug '{new_slug}' уже существует.",
                    )
                brand.slug = new_slug

        if "logo_url" in payload:
            brand.logo_url = payload["logo_url"]
        if "description" in payload:
            brand.description = payload["description"]
        if "is_published" in payload and payload["is_published"] is not None:
            brand.is_published = bool(payload["is_published"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            brand.sort_order = int(payload["sort_order"])

        session.add(brand)
        await session.flush()

        await ManagerBrandService._sync_brand_tag(session, brand=brand, previous_slug=previous_slug)

        changed_slugs = [previous_slug]
        if brand.slug != previous_slug:
            changed_slugs.append(brand.slug)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_update",
            brand_slugs=changed_slugs,
        )
        await session.commit()
        await session.refresh(brand)

        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.brand_id == brand.id)
            )
        ).scalar_one()
        return ManagerBrandService._serialize_brand(brand, products_count=int(products_count or 0))

    @staticmethod
    async def delete_brand(
        session: AsyncSession,
        brand_id: int,
    ) -> None:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.brand_id == brand_id)
            )
        ).scalar_one()
        if int(products_count or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить бренд: к нему привязаны товары.",
            )

        series_count = (
            await session.execute(
                select(func.count(ProductSeries.id)).where(ProductSeries.brand_id == brand_id)
            )
        ).scalar_one()
        if int(series_count or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить бренд: к нему привязаны серии.",
            )

        brand_tag = (
            await session.execute(
                select(Tag)
                .join(TagGroup, Tag.group_id == TagGroup.id)
                .where(Tag.slug == brand.slug, TagGroup.slug == "brand")
            )
        ).scalar_one_or_none()
        if brand_tag is not None:
            link_count = (
                await session.execute(
                    select(func.count(ProductTagLink.product_id)).where(
                        ProductTagLink.tag_id == brand_tag.id
                    )
                )
            ).scalar_one()
            if int(link_count or 0) > 0:
                raise HTTPException(
                    status_code=400,
                    detail="Нельзя удалить бренд: у тега бренда есть привязанные товары.",
                )
            await session.delete(brand_tag)

        brand_slug = brand.slug

        await session.delete(brand)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_delete",
            brand_slugs=[brand_slug],
        )
        await session.commit()

    @staticmethod
    async def list_brand_series(
        session: AsyncSession,
        brand_id: int,
    ) -> List[Dict[str, Any]]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        await ManagerBrandService._sync_missing_product_series_for_brand(
            session,
            brand=brand,
        )

        rows = (
            await session.execute(
                select(ProductSeries, func.count(Product.id).label("products_count"))
                .outerjoin(Product, Product.series_id == ProductSeries.id)
                .where(ProductSeries.brand_id == brand_id)
                .group_by(ProductSeries.id)
                .order_by(ProductSeries.sort_order.asc(), ProductSeries.title.asc())
            )
        ).all()
        feature_map = await ManagerBrandService._load_series_brand_features(
            session,
            [series.id for series, _ in rows if series.id is not None],
        )
        return [
            ManagerBrandService._serialize_series(
                series,
                products_count=int(products_count or 0),
                brand_features=feature_map.get(int(series.id or 0), []),
            )
            for series, products_count in rows
        ]

    @staticmethod
    async def _sync_missing_product_series_for_brand(
        session: AsyncSession,
        *,
        brand: Brand,
    ) -> int:
        products = (
            await session.execute(
                select(Product).where(
                    Product.brand_id == brand.id,
                    Product.series_id.is_(None),
                )
            )
        ).scalars().all()

        changed_product_ids: List[int] = []
        for product in products:
            if not extract_series_name(specs=product.specs or {}):
                continue

            if await sync_product_brand_series(
                session,
                product=product,
                specs=product.specs or {},
                title=product.title or "",
                explicit_brand_id=brand.id,
                explicit_brand_override=True,
            ):
                if product.id is not None:
                    changed_product_ids.append(int(product.id))

        if not changed_product_ids:
            return 0

        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_series_auto_sync",
            product_ids=changed_product_ids,
            brand_slugs=[brand.slug],
        )
        await session.commit()
        return len(changed_product_ids)

    @staticmethod
    async def create_brand_series(
        session: AsyncSession,
        brand_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Название серии не может быть пустым.")

        series_slug = ManagerBrandService._build_series_slug(payload.get("slug"), title)
        await ManagerBrandService._ensure_series_slug_available(
            session,
            brand_id=brand_id,
            slug=series_slug,
        )

        series = ProductSeries(
            brand_id=brand_id,
            title=title,
            slug=series_slug,
            tagline=ManagerBrandService._clean_optional_text(payload.get("tagline")),
            short_description=ManagerBrandService._clean_optional_text(payload.get("short_description")),
            description=ManagerBrandService._clean_optional_text(payload.get("description")),
            hero_image=ManagerBrandService._clean_optional_text(payload.get("hero_image")),
            gallery_images=ManagerBrandService._normalize_string_list(payload.get("gallery_images")),
            features=ManagerBrandService._normalize_features(payload.get("features")),
            feature_blocks=ManagerBrandService._normalize_feature_blocks(payload.get("feature_blocks")),
            content_blocks=ManagerBrandService._normalize_content_blocks(payload.get("content_blocks")),
            footnotes=ManagerBrandService._normalize_string_list(payload.get("footnotes")),
            seo_title=ManagerBrandService._clean_optional_text(payload.get("seo_title")),
            seo_description=ManagerBrandService._clean_optional_text(payload.get("seo_description")),
            source_url=ManagerBrandService._clean_optional_text(payload.get("source_url")),
            is_published=bool(payload.get("is_published", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        session.add(series)
        await session.flush()
        if "brand_feature_ids" in payload and payload["brand_feature_ids"] is not None:
            await ManagerBrandService._sync_series_brand_features(
                session,
                series=series,
                brand_id=brand_id,
                feature_ids=payload.get("brand_feature_ids"),
            )

        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_series_create",
            brand_slugs=[brand.slug],
        )
        await session.commit()
        await session.refresh(series)
        feature_map = await ManagerBrandService._load_series_brand_features(session, [int(series.id or 0)])
        return ManagerBrandService._serialize_series(
            series,
            products_count=0,
            brand_features=feature_map.get(int(series.id or 0), []),
        )

    @staticmethod
    async def update_brand_series(
        session: AsyncSession,
        brand_id: int,
        series_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await ManagerBrandService._get_brand_series(session, brand_id, series_id)

        if "title" in payload and payload["title"] is not None:
            title = str(payload["title"]).strip()
            if not title:
                raise HTTPException(status_code=400, detail="Название серии не может быть пустым.")
            series.title = title

        if "slug" in payload and payload["slug"] is not None:
            new_slug = ManagerBrandService._build_series_slug(payload["slug"], series.title)
            if new_slug != series.slug:
                await ManagerBrandService._ensure_series_slug_available(
                    session,
                    brand_id=brand_id,
                    slug=new_slug,
                    exclude_series_id=series_id,
                )
                series.slug = new_slug

        if "tagline" in payload:
            series.tagline = ManagerBrandService._clean_optional_text(payload["tagline"])
        if "short_description" in payload:
            series.short_description = ManagerBrandService._clean_optional_text(payload["short_description"])
        if "description" in payload:
            series.description = ManagerBrandService._clean_optional_text(payload["description"])
        if "hero_image" in payload:
            series.hero_image = ManagerBrandService._clean_optional_text(payload["hero_image"])
        if "gallery_images" in payload and payload["gallery_images"] is not None:
            series.gallery_images = ManagerBrandService._normalize_string_list(payload["gallery_images"])
        if "features" in payload and payload["features"] is not None:
            series.features = ManagerBrandService._normalize_features(payload["features"])
        if "feature_blocks" in payload and payload["feature_blocks"] is not None:
            series.feature_blocks = ManagerBrandService._normalize_feature_blocks(payload["feature_blocks"])
        if "content_blocks" in payload and payload["content_blocks"] is not None:
            series.content_blocks = ManagerBrandService._normalize_content_blocks(payload["content_blocks"])
        if "footnotes" in payload and payload["footnotes"] is not None:
            series.footnotes = ManagerBrandService._normalize_string_list(payload["footnotes"])
        if "seo_title" in payload:
            series.seo_title = ManagerBrandService._clean_optional_text(payload["seo_title"])
        if "seo_description" in payload:
            series.seo_description = ManagerBrandService._clean_optional_text(payload["seo_description"])
        if "source_url" in payload:
            series.source_url = ManagerBrandService._clean_optional_text(payload["source_url"])
        if "is_published" in payload and payload["is_published"] is not None:
            series.is_published = bool(payload["is_published"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            series.sort_order = int(payload["sort_order"])

        session.add(series)
        await session.flush()
        if "brand_feature_ids" in payload and payload["brand_feature_ids"] is not None:
            await ManagerBrandService._sync_series_brand_features(
                session,
                series=series,
                brand_id=brand_id,
                feature_ids=payload.get("brand_feature_ids"),
            )

        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_series_update",
            brand_slugs=[brand.slug],
        )
        await session.commit()
        await session.refresh(series)

        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.series_id == series.id)
            )
        ).scalar_one()
        feature_map = await ManagerBrandService._load_series_brand_features(session, [int(series.id or 0)])
        return ManagerBrandService._serialize_series(
            series,
            products_count=int(products_count or 0),
            brand_features=feature_map.get(int(series.id or 0), []),
        )

    @staticmethod
    async def apply_series_gallery_to_products(
        session: AsyncSession,
        brand_id: int,
        series_id: int,
        source_urls: List[str],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await ManagerBrandService._get_brand_series(session, brand_id, series_id)
        gallery_urls = ManagerBrandService._normalize_string_list(source_urls)
        if not gallery_urls:
            raise HTTPException(status_code=400, detail="Галерея серии пуста.")

        product_ids = list(
            (
                await session.execute(
                    select(Product.id).where(Product.series_id == series.id).order_by(Product.id)
                )
            ).scalars().all()
        )
        series.gallery_images = gallery_urls
        session.add(series)

        if product_ids:
            from services.manager_media_service import ManagerMediaService

            result = await ManagerMediaService.bulk_add_gallery_images(
                session=session,
                product_ids=product_ids,
                source_urls=gallery_urls,
                is_installation=False,
                skip_existing=True,
                set_main=False,
                commit=False,
            )
        else:
            result = {
                "message": "Series gallery saved; no products assigned",
                "products_count": 0,
                "added_links": 0,
                "skipped_existing": 0,
            }

        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_series_gallery_apply",
            product_ids=product_ids,
            brand_slugs=[brand.slug],
        )
        await session.commit()
        return {
            **result,
            "series_id": int(series.id or series_id),
            "images_applied": len(gallery_urls),
        }

    @staticmethod
    async def delete_brand_series(
        session: AsyncSession,
        brand_id: int,
        series_id: int,
    ) -> None:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await ManagerBrandService._get_brand_series(session, brand_id, series_id)
        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.series_id == series.id)
            )
        ).scalar_one()
        if int(products_count or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить серию: к ней привязаны товары. Скройте серию вместо удаления.",
            )

        link_rows = (
            await session.execute(
                select(FeatureSeriesLink).where(FeatureSeriesLink.series_id == series.id)
            )
        ).scalars().all()
        for link in link_rows:
            await session.delete(link)
        await session.delete(series)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="brand_series_delete",
            brand_slugs=[brand.slug],
        )
        await session.commit()

    @staticmethod
    def _serialize_brand(brand: Brand, *, products_count: int = 0) -> Dict[str, Any]:
        return {
            "id": brand.id,
            "title": brand.title,
            "slug": brand.slug,
            "logo_url": brand.logo_url,
            "description": brand.description,
            "is_published": brand.is_published,
            "sort_order": brand.sort_order,
            "created_at": brand.created_at,
            "products_count": int(products_count or 0),
        }

    @staticmethod
    def _serialize_series(
        series: ProductSeries,
        *,
        products_count: int = 0,
        brand_features: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        selected_features = brand_features or []
        return {
            "id": series.id,
            "brand_id": series.brand_id,
            "title": series.title,
            "slug": series.slug,
            "tagline": series.tagline,
            "short_description": series.short_description,
            "description": series.description,
            "hero_image": series.hero_image,
            "gallery_images": ManagerBrandService._normalize_string_list(series.gallery_images),
            "features": ManagerBrandService._normalize_features(series.features),
            "brand_features": selected_features,
            "brand_feature_ids": [int(item["id"]) for item in selected_features if item.get("id") is not None],
            "feature_blocks": ManagerBrandService._normalize_feature_blocks(series.feature_blocks),
            "content_blocks": ManagerBrandService._normalize_content_blocks(series.content_blocks),
            "footnotes": ManagerBrandService._normalize_string_list(series.footnotes),
            "seo_title": series.seo_title,
            "seo_description": series.seo_description,
            "source_url": series.source_url,
            "is_published": series.is_published,
            "sort_order": series.sort_order,
            "created_at": series.created_at,
            "products_count": int(products_count or 0),
        }

    @staticmethod
    def _serialize_brand_feature(feature: Feature, *, series_count: int = 0) -> Dict[str, Any]:
        return {
            "id": feature.id,
            "brand_id": feature.brand_id,
            "title": feature.name,
            "slug": feature.slug,
            "text": feature.full_description,
            "image_url": feature.image_url,
            "icon": feature.icon,
            "footnote": feature.footnote,
            "source_url": feature.source_url,
            "aliases": ManagerBrandService._normalize_string_list(feature.aliases),
            "is_published": feature.is_active,
            "sort_order": int(feature.sort_order or 0),
            "created_at": feature.created_at,
            "updated_at": feature.updated_at,
            "series_count": int(series_count or 0),
        }

    @staticmethod
    def _serialize_series_feature_link(
        link: FeatureSeriesLink,
        feature: Feature,
    ) -> Dict[str, Any]:
        return {
            "id": feature.id,
            "title": link.override_title or feature.name,
            "slug": feature.slug,
            "text": link.override_description if link.override_description is not None else feature.full_description,
            "image_url": link.override_image_url or feature.image_url,
            "icon": link.override_icon or feature.icon,
            "footnote": link.override_footnote or feature.footnote,
            "source_url": feature.source_url,
            "aliases": ManagerBrandService._normalize_string_list(feature.aliases),
            "is_published": feature.is_active,
            "sort_order": int(link.sort_order if link.sort_order is not None else feature.sort_order or 0),
        }

    @staticmethod
    async def _load_series_brand_features(
        session: AsyncSession,
        series_ids: List[int],
    ) -> Dict[int, List[Dict[str, Any]]]:
        normalized_ids = [int(value) for value in dict.fromkeys(series_ids) if value]
        if not normalized_ids:
            return {}

        rows = (
            await session.execute(
                select(FeatureSeriesLink, Feature, ProductSeries.brand_id)
                .join(Feature, Feature.id == FeatureSeriesLink.feature_id)
                .join(ProductSeries, ProductSeries.id == FeatureSeriesLink.series_id)
                .where(FeatureSeriesLink.series_id.in_(normalized_ids))
                .order_by(
                    FeatureSeriesLink.series_id.asc(),
                    FeatureSeriesLink.sort_order.asc(),
                    Feature.sort_order.asc(),
                    Feature.name.asc(),
                )
            )
        ).all()
        out: Dict[int, List[Dict[str, Any]]] = {series_id: [] for series_id in normalized_ids}
        for link, feature, brand_id in rows:
            if not FeatureScopePolicy.allows_target(
                feature,
                target_type="series",
                brand_id=brand_id,
            ):
                continue
            out.setdefault(int(link.series_id), []).append(
                ManagerBrandService._serialize_series_feature_link(link, feature)
            )
        return out

    @staticmethod
    async def _sync_series_brand_features(
        session: AsyncSession,
        *,
        series: ProductSeries,
        brand_id: int,
        feature_ids: Any,
    ) -> None:
        if not series.id:
            return

        normalized_ids: List[int] = []
        for value in feature_ids or []:
            try:
                feature_id = int(value)
            except (TypeError, ValueError):
                continue
            if feature_id > 0 and feature_id not in normalized_ids:
                normalized_ids.append(feature_id)

        if normalized_ids:
            candidates = list(
                (
                    await session.execute(
                        select(Feature).where(
                            Feature.id.in_(normalized_ids),
                            Feature.is_active.is_(True),
                            Feature.archived_at.is_(None),
                        )
                    )
                ).scalars().all()
            )
            found_ids = {
                int(feature.id)
                for feature in candidates
                if FeatureScopePolicy.allows_target(
                    feature,
                    target_type="series",
                    brand_id=brand_id,
                )
            }
            missing_ids = [feature_id for feature_id in normalized_ids if feature_id not in found_ids]
            if missing_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Фичи не найдены у этого бренда: {', '.join(map(str, missing_ids))}",
                )

        existing_links = (
            await session.execute(
                select(FeatureSeriesLink).where(FeatureSeriesLink.series_id == series.id)
            )
        ).scalars().all()
        existing_by_feature_id = {int(link.feature_id): link for link in existing_links}
        keep_ids = set(normalized_ids)

        for link in existing_links:
            if int(link.feature_id) not in keep_ids:
                await session.delete(link)

        for index, feature_id in enumerate(normalized_ids):
            link = existing_by_feature_id.get(feature_id)
            if link is None:
                link = FeatureSeriesLink(
                    series_id=int(series.id),
                    feature_id=feature_id,
                )
            link.sort_order = (index + 1) * 10
            session.add(link)

    @staticmethod
    async def _brand_feature_series_count(session: AsyncSession, feature_id: int) -> int:
        count = (
            await session.execute(
                select(func.count(FeatureSeriesLink.id)).where(
                    FeatureSeriesLink.feature_id == feature_id
                )
            )
        ).scalar_one()
        return int(count or 0)

    @staticmethod
    async def _get_brand_feature(
        session: AsyncSession,
        brand_id: int,
        feature_id: int,
    ) -> Feature:
        feature = (
            await session.execute(
                select(Feature).where(
                    Feature.id == feature_id,
                    Feature.brand_id == brand_id,
                )
            )
        ).scalar_one_or_none()
        if feature is None:
            raise HTTPException(status_code=404, detail="Фича не найдена.")
        return feature

    @staticmethod
    async def _get_brand_series(
        session: AsyncSession,
        brand_id: int,
        series_id: int,
    ) -> ProductSeries:
        series = (
            await session.execute(
                select(ProductSeries).where(
                    ProductSeries.id == series_id,
                    ProductSeries.brand_id == brand_id,
                )
            )
        ).scalar_one_or_none()
        if series is None:
            raise HTTPException(status_code=404, detail="Серия не найдена.")
        return series

    @staticmethod
    async def _ensure_series_slug_available(
        session: AsyncSession,
        *,
        brand_id: int,
        slug: str,
        exclude_series_id: Optional[int] = None,
    ) -> None:
        query = select(ProductSeries).where(
            ProductSeries.brand_id == brand_id,
            ProductSeries.slug == slug,
        )
        if exclude_series_id is not None:
            query = query.where(ProductSeries.id != exclude_series_id)
        existing = (await session.execute(query)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Серия со slug '{slug}' уже существует у этого бренда.",
            )

    @staticmethod
    async def _ensure_brand_feature_slug_available(
        session: AsyncSession,
        *,
        brand_id: int,
        slug: str,
        exclude_feature_id: Optional[int] = None,
    ) -> None:
        query = select(Feature).where(Feature.slug == slug)
        if exclude_feature_id is not None:
            query = query.where(Feature.id != exclude_feature_id)
        existing = (await session.execute(query)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Фича со slug '{slug}' уже существует у этого бренда.",
            )

    @staticmethod
    def _build_series_slug(value: Any, fallback_title: str) -> str:
        requested_slug = str(value or "").strip()
        series_slug = requested_slug or slugify(fallback_title, lowercase=True)
        if not series_slug:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug серии.")
        return series_slug

    @staticmethod
    def _build_feature_slug(value: Any, fallback_title: str) -> str:
        requested_slug = str(value or "").strip()
        feature_slug = requested_slug or slugify(fallback_title, lowercase=True)
        if not feature_slug:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug фичи.")
        return feature_slug

    @staticmethod
    def _clean_optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_features(value: Any) -> List[str]:
        return ManagerBrandService._normalize_string_list(value)

    @staticmethod
    def _normalize_string_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []

        items: List[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            dedupe_key = text.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(text)
        return items

    @staticmethod
    def _normalize_feature_blocks(value: Any) -> List[Dict[str, Optional[str]]]:
        if not isinstance(value, list):
            return []

        blocks: List[Dict[str, Optional[str]]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            title = ManagerBrandService._clean_optional_text(item.get("title"))
            if not title:
                continue
            blocks.append(
                {
                    "title": title,
                    "text": ManagerBrandService._clean_optional_text(item.get("text")),
                    "image_url": ManagerBrandService._clean_optional_text(item.get("image_url")),
                    "icon": ManagerBrandService._clean_optional_text(item.get("icon")),
                    "footnote": ManagerBrandService._clean_optional_text(item.get("footnote")),
                }
            )
        return blocks

    @staticmethod
    def _normalize_content_blocks(value: Any) -> List[Dict[str, Optional[str]]]:
        if not isinstance(value, list):
            return []

        allowed_kinds = {"text", "image_text", "media"}
        allowed_layouts = {"text_left", "text_right", "full"}
        blocks: List[Dict[str, Optional[str]]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            title = ManagerBrandService._clean_optional_text(item.get("title"))
            text = ManagerBrandService._clean_optional_text(item.get("text"))
            image_url = ManagerBrandService._clean_optional_text(item.get("image_url"))
            if not any((title, text, image_url)):
                continue
            kind = str(item.get("kind") or "text").strip()
            layout = str(item.get("layout") or "text_left").strip()
            blocks.append(
                {
                    "kind": kind if kind in allowed_kinds else "text",
                    "title": title,
                    "text": text,
                    "image_url": image_url,
                    "layout": layout if layout in allowed_layouts else "text_left",
                }
            )
        return blocks

    @staticmethod
    async def _ensure_brand_group(session: AsyncSession) -> TagGroup:
        group = (
            await session.execute(select(TagGroup).where(TagGroup.slug == "brand"))
        ).scalar_one_or_none()
        if group is not None:
            return group

        group = TagGroup(
            title="Бренд",
            slug="brand",
            is_public=True,
            color="teal",
            allow_multiple=False,
        )
        session.add(group)
        await session.flush()
        return group

    @staticmethod
    async def _sync_brand_tag(
        session: AsyncSession,
        *,
        brand: Brand,
        previous_slug: Optional[str],
    ) -> None:
        if not brand.slug:
            return

        brand_group = await ManagerBrandService._ensure_brand_group(session)

        tag: Optional[Tag] = None
        if previous_slug and previous_slug != brand.slug:
            tag = (
                await session.execute(
                    select(Tag).where(Tag.slug == previous_slug, Tag.group_id == brand_group.id)
                )
            ).scalar_one_or_none()

        if tag is None:
            same_slug_tag = (
                await session.execute(select(Tag).where(Tag.slug == brand.slug))
            ).scalar_one_or_none()
            if same_slug_tag is not None and same_slug_tag.group_id != brand_group.id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Slug '{brand.slug}' уже занят тегом в другой группе. "
                        "Обновите slug бренда."
                    ),
                )
            tag = same_slug_tag

        if tag is None:
            tag = Tag(
                group_id=brand_group.id,
                title=brand.title,
                slug=brand.slug,
                is_public=True,
                is_filter=True,
            )
            session.add(tag)
            await session.flush()
            return

        tag.group_id = brand_group.id
        tag.title = brand.title
        tag.slug = brand.slug
        tag.is_public = True
        tag.is_filter = True
        session.add(tag)
        await session.flush()
