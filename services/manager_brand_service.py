from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup


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

        await session.delete(brand)
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
