from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup
from services.catalog_revision_service import CatalogRevisionService


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
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_create",
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
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_update",
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
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_delete",
            brand_slugs=[brand_slug],
        )

    @staticmethod
    async def list_brand_series(
        session: AsyncSession,
        brand_id: int,
    ) -> List[Dict[str, Any]]:
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Бренд не найден.")

        rows = (
            await session.execute(
                select(ProductSeries, func.count(Product.id).label("products_count"))
                .outerjoin(Product, Product.series_id == ProductSeries.id)
                .where(ProductSeries.brand_id == brand_id)
                .group_by(ProductSeries.id)
                .order_by(ProductSeries.sort_order.asc(), ProductSeries.title.asc())
            )
        ).all()
        return [
            ManagerBrandService._serialize_series(series, products_count=int(products_count or 0))
            for series, products_count in rows
        ]

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
            description=ManagerBrandService._clean_optional_text(payload.get("description")),
            hero_image=ManagerBrandService._clean_optional_text(payload.get("hero_image")),
            features=ManagerBrandService._normalize_features(payload.get("features")),
            is_published=bool(payload.get("is_published", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        session.add(series)
        await session.flush()

        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_series_create",
            brand_slugs=[brand.slug],
        )
        await session.refresh(series)
        return ManagerBrandService._serialize_series(series, products_count=0)

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

        if "description" in payload:
            series.description = ManagerBrandService._clean_optional_text(payload["description"])
        if "hero_image" in payload:
            series.hero_image = ManagerBrandService._clean_optional_text(payload["hero_image"])
        if "features" in payload and payload["features"] is not None:
            series.features = ManagerBrandService._normalize_features(payload["features"])
        if "is_published" in payload and payload["is_published"] is not None:
            series.is_published = bool(payload["is_published"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            series.sort_order = int(payload["sort_order"])

        session.add(series)
        await session.flush()

        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_series_update",
            brand_slugs=[brand.slug],
        )
        await session.refresh(series)

        products_count = (
            await session.execute(
                select(func.count(Product.id)).where(Product.series_id == series.id)
            )
        ).scalar_one()
        return ManagerBrandService._serialize_series(series, products_count=int(products_count or 0))

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

        await session.delete(series)
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="brand_series_delete",
            brand_slugs=[brand.slug],
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
    def _serialize_series(series: ProductSeries, *, products_count: int = 0) -> Dict[str, Any]:
        return {
            "id": series.id,
            "brand_id": series.brand_id,
            "title": series.title,
            "slug": series.slug,
            "description": series.description,
            "hero_image": series.hero_image,
            "features": ManagerBrandService._normalize_features(series.features),
            "is_published": series.is_published,
            "sort_order": series.sort_order,
            "created_at": series.created_at,
            "products_count": int(products_count or 0),
        }

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
    def _build_series_slug(value: Any, fallback_title: str) -> str:
        requested_slug = str(value or "").strip()
        series_slug = requested_slug or slugify(fallback_title, lowercase=True)
        if not series_slug:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug серии.")
        return series_slug

    @staticmethod
    def _clean_optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_features(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []

        features: List[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            dedupe_key = text.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            features.append(text)
        return features

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
