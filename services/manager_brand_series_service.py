from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, Feature, FeatureSeriesLink, Product, ProductSeries
from services.brand_series_service import extract_series_name, sync_product_brand_series
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.catalog_mutation_contracts import CatalogMutationBatch
from services.feature_scope_policy import FeatureScopePolicy


class ManagerBrandSeriesOperations:
    @classmethod
    async def list_brand_series(
        cls,
        session: AsyncSession,
        brand_id: int,
    ) -> List[Dict[str, Any]]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        await cls._sync_missing_product_series_for_brand(
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
        feature_map = await cls._load_series_brand_features(
            session,
            [series.id for series, _ in rows if series.id is not None],
        )
        return [
            cls._serialize_series(
                series,
                products_count=int(products_count or 0),
                brand_features=feature_map.get(int(series.id or 0), []),
            )
            for series, products_count in rows
        ]

    @classmethod
    async def _sync_missing_product_series_for_brand(
        cls,
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

        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="brand_series_auto_sync",
            product_ids=changed_product_ids,
            brand_slugs=[brand.slug],
        )
        return len(changed_product_ids)

    @classmethod
    async def create_brand_series(
        cls,
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

        series_slug = cls._build_series_slug(payload.get("slug"), title)
        await cls._ensure_series_slug_available(
            session,
            brand_id=brand_id,
            slug=series_slug,
        )

        series = ProductSeries(
            brand_id=brand_id,
            title=title,
            slug=series_slug,
            tagline=cls._clean_optional_text(payload.get("tagline")),
            short_description=cls._clean_optional_text(payload.get("short_description")),
            description=cls._clean_optional_text(payload.get("description")),
            hero_image=cls._clean_optional_text(payload.get("hero_image")),
            gallery_images=cls._normalize_string_list(payload.get("gallery_images")),
            features=cls._normalize_features(payload.get("features")),
            feature_blocks=cls._normalize_feature_blocks(payload.get("feature_blocks")),
            content_blocks=cls._normalize_content_blocks(payload.get("content_blocks")),
            footnotes=cls._normalize_string_list(payload.get("footnotes")),
            seo_title=cls._clean_optional_text(payload.get("seo_title")),
            seo_description=cls._clean_optional_text(payload.get("seo_description")),
            source_url=cls._clean_optional_text(payload.get("source_url")),
            is_published=bool(payload.get("is_published", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        session.add(series)
        await session.flush()
        if "brand_feature_ids" in payload and payload["brand_feature_ids"] is not None:
            await cls._sync_series_brand_features(
                session,
                series=series,
                brand_id=brand_id,
                feature_ids=payload.get("brand_feature_ids"),
            )

        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="brand_series_create",
            brand_slugs=[brand.slug],
        )
        await session.refresh(series)
        feature_map = await cls._load_series_brand_features(session, [int(series.id or 0)])
        return cls._serialize_series(
            series,
            products_count=0,
            brand_features=feature_map.get(int(series.id or 0), []),
        )

    @classmethod
    async def update_brand_series(
        cls,
        session: AsyncSession,
        brand_id: int,
        series_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await cls._get_brand_series(session, brand_id, series_id)

        if "title" in payload and payload["title"] is not None:
            title = str(payload["title"]).strip()
            if not title:
                raise HTTPException(status_code=400, detail="Название серии не может быть пустым.")
            series.title = title

        if "slug" in payload and payload["slug"] is not None:
            new_slug = cls._build_series_slug(payload["slug"], series.title)
            if new_slug != series.slug:
                await cls._ensure_series_slug_available(
                    session,
                    brand_id=brand_id,
                    slug=new_slug,
                    exclude_series_id=series_id,
                )
                series.slug = new_slug

        if "tagline" in payload:
            series.tagline = cls._clean_optional_text(payload["tagline"])
        if "short_description" in payload:
            series.short_description = cls._clean_optional_text(payload["short_description"])
        if "description" in payload:
            series.description = cls._clean_optional_text(payload["description"])
        if "hero_image" in payload:
            series.hero_image = cls._clean_optional_text(payload["hero_image"])
        if "gallery_images" in payload and payload["gallery_images"] is not None:
            series.gallery_images = cls._normalize_string_list(payload["gallery_images"])
        if "features" in payload and payload["features"] is not None:
            series.features = cls._normalize_features(payload["features"])
        if "feature_blocks" in payload and payload["feature_blocks"] is not None:
            series.feature_blocks = cls._normalize_feature_blocks(payload["feature_blocks"])
        if "content_blocks" in payload and payload["content_blocks"] is not None:
            series.content_blocks = cls._normalize_content_blocks(payload["content_blocks"])
        if "footnotes" in payload and payload["footnotes"] is not None:
            series.footnotes = cls._normalize_string_list(payload["footnotes"])
        if "seo_title" in payload:
            series.seo_title = cls._clean_optional_text(payload["seo_title"])
        if "seo_description" in payload:
            series.seo_description = cls._clean_optional_text(payload["seo_description"])
        if "source_url" in payload:
            series.source_url = cls._clean_optional_text(payload["source_url"])
        if "is_published" in payload and payload["is_published"] is not None:
            series.is_published = bool(payload["is_published"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            series.sort_order = int(payload["sort_order"])

        session.add(series)
        await session.flush()
        if "brand_feature_ids" in payload and payload["brand_feature_ids"] is not None:
            await cls._sync_series_brand_features(
                session,
                series=series,
                brand_id=brand_id,
                feature_ids=payload.get("brand_feature_ids"),
            )

        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="brand_series_update",
            brand_slugs=[brand.slug],
        )
        await session.refresh(series)

        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.series_id == series.id)
            )
        ).scalar_one()
        feature_map = await cls._load_series_brand_features(session, [int(series.id or 0)])
        return cls._serialize_series(
            series,
            products_count=int(products_count or 0),
            brand_features=feature_map.get(int(series.id or 0), []),
        )

    @classmethod
    async def apply_series_gallery_to_products(
        cls,
        session: AsyncSession,
        brand_id: int,
        series_id: int,
        source_urls: List[str],
    ) -> Dict[str, Any]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await cls._get_brand_series(session, brand_id, series_id)
        gallery_urls = cls._normalize_string_list(source_urls)
        if not gallery_urls:
            raise HTTPException(status_code=400, detail="Галерея серии пуста.")

        product_ids = list(
            (
                await session.execute(
                    select(Product.id).where(Product.series_id == series.id).order_by(Product.id)
                )
            ).scalars().all()
        )
        series_changed = list(series.gallery_images or []) != gallery_urls
        if series_changed:
            series.gallery_images = gallery_urls
            session.add(series)

        mutation_batch = CatalogMutationBatch()
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
                mutation_batch=mutation_batch,
            )
        else:
            result = {
                "message": "Series gallery saved; no products assigned",
                "products_count": 0,
                "added_links": 0,
                "skipped_existing": 0,
            }

        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.apply_series_gallery_to_products",
            changed=series_changed or mutation_batch.changed,
            product_ids=product_ids,
            brand_slugs=[brand.slug],
        )
        return {
            **result,
            "series_id": int(series.id or series_id),
            "images_applied": len(gallery_urls),
        }

    @classmethod
    async def delete_brand_series(
        cls,
        session: AsyncSession,
        brand_id: int,
        series_id: int,
    ) -> None:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        series = await cls._get_brand_series(session, brand_id, series_id)
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
        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="brand_series_delete",
            brand_slugs=[brand.slug],
        )

    @classmethod
    def _serialize_series(
        cls,
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
            "gallery_images": cls._normalize_string_list(series.gallery_images),
            "features": cls._normalize_features(series.features),
            "brand_features": selected_features,
            "brand_feature_ids": [int(item["id"]) for item in selected_features if item.get("id") is not None],
            "feature_blocks": cls._normalize_feature_blocks(series.feature_blocks),
            "content_blocks": cls._normalize_content_blocks(series.content_blocks),
            "footnotes": cls._normalize_string_list(series.footnotes),
            "seo_title": series.seo_title,
            "seo_description": series.seo_description,
            "source_url": series.source_url,
            "is_published": series.is_published,
            "sort_order": series.sort_order,
            "created_at": series.created_at,
            "products_count": int(products_count or 0),
        }

    @classmethod
    def _serialize_series_feature_link(
        cls,
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
            "aliases": cls._normalize_string_list(feature.aliases),
            "is_published": feature.is_active,
            "sort_order": int(link.sort_order if link.sort_order is not None else feature.sort_order or 0),
        }

    @classmethod
    async def _load_series_brand_features(
        cls,
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
                cls._serialize_series_feature_link(link, feature)
            )
        return out

    @classmethod
    async def _sync_series_brand_features(
        cls,
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

    @classmethod
    async def _get_brand_series(
        cls,
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

    @classmethod
    async def _ensure_series_slug_available(
        cls,
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

    @classmethod
    def _build_series_slug(cls, value: Any, fallback_title: str) -> str:
        requested_slug = str(value or "").strip()
        series_slug = requested_slug or slugify(fallback_title, lowercase=True)
        if not series_slug:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug серии.")
        return series_slug
