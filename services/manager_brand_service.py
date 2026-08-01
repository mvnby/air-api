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
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.manager_brand_series_service import ManagerBrandSeriesOperations


class ManagerBrandService(ManagerBrandSeriesOperations):
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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.create_brand_feature",
            changed=True,
            brand_slugs=[brand.slug],
        )
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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.update_brand_feature",
            changed=True,
            brand_slugs=[brand.slug],
        )
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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.delete_brand_feature",
            changed=True,
            brand_slugs=[brand.slug],
        )

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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.create_brand",
            changed=True,
            brand_slugs=[brand.slug],
        )
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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.update_brand",
            changed=True,
            brand_slugs=changed_slugs,
        )
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
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_brand.delete_brand",
            changed=True,
            brand_slugs=[brand_slug],
        )

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
