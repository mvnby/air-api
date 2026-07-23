from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product import ProductDAO
from crud.product_collection import ProductCollectionDAO
from models import ProductCollection
from services.product_collection_resolver import ProductCollectionResolver


KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ManagerProductCollectionService:
    @staticmethod
    async def list_collections(session: AsyncSession) -> list[dict]:
        rows = await ProductCollectionDAO.list_all(session)
        return [ManagerProductCollectionService._serialize(row) for row in rows]

    @staticmethod
    async def get_collection(
        session: AsyncSession,
        collection_id: int,
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        return ManagerProductCollectionService._serialize(collection)

    @staticmethod
    async def create_collection(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> dict:
        data = ManagerProductCollectionService._clean_fields(payload)
        ManagerProductCollectionService._validate_required_text(data)
        data["slug"] = await ManagerProductCollectionService._unique_slug(
            session,
            requested=data.get("slug"),
            fallback=data["internal_name"],
        )
        await ManagerProductCollectionService._validate_fallback(
            session,
            fallback_id=data.get("fallback_collection_id"),
        )
        collection = ProductCollection(**data)
        session.add(collection)
        await session.commit()
        return await ManagerProductCollectionService.get_collection(
            session,
            int(collection.id),
        )

    @staticmethod
    async def update_collection(
        session: AsyncSession,
        collection_id: int,
        payload: dict[str, Any],
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        data = ManagerProductCollectionService._clean_fields(payload)
        ManagerProductCollectionService._validate_required_text(data)
        if "slug" in data:
            data["slug"] = await ManagerProductCollectionService._unique_slug(
                session,
                requested=data["slug"],
                fallback=data.get("internal_name") or collection.internal_name,
                exclude_id=collection_id,
            )
        fallback_id = data.get("fallback_collection_id")
        if fallback_id == collection_id:
            raise HTTPException(status_code=400, detail="Подборка не может ссылаться сама на себя.")
        if "fallback_collection_id" in data:
            await ManagerProductCollectionService._validate_fallback(
                session,
                fallback_id=fallback_id,
            )

        min_items = int(data.get("min_items", collection.min_items))
        max_items = int(data.get("max_items", collection.max_items))
        if max_items < min_items:
            raise HTTPException(
                status_code=400,
                detail="Максимальное количество не может быть меньше минимального.",
            )
        starts_at = data.get("starts_at", collection.starts_at)
        ends_at = data.get("ends_at", collection.ends_at)
        if starts_at and ends_at and ends_at <= starts_at:
            raise HTTPException(status_code=400, detail="Дата окончания должна быть позже начала.")

        for field, value in data.items():
            setattr(collection, field, value)
        collection.updated_at = utc_now()
        session.add(collection)
        await session.commit()
        return await ManagerProductCollectionService.get_collection(session, collection_id)

    @staticmethod
    async def replace_items(
        session: AsyncSession,
        collection_id: int,
        items: list[dict],
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        product_ids = [int(item["product_id"]) for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise HTTPException(status_code=400, detail="Один товар нельзя добавить дважды.")
        products = await ProductDAO.get_by_ids(session, product_ids)
        if len(products) != len(product_ids):
            found_ids = {int(product.id) for product in products}
            missing = [product_id for product_id in product_ids if product_id not in found_ids]
            raise HTTPException(
                status_code=400,
                detail=f"Не найдены товары: {', '.join(map(str, missing))}.",
            )
        await ProductCollectionDAO.replace_items(
            session,
            collection_id=collection_id,
            items=items,
        )
        collection.updated_at = utc_now()
        session.add(collection)
        await session.commit()
        return await ManagerProductCollectionService.get_collection(session, collection_id)

    @staticmethod
    async def replace_placements(
        session: AsyncSession,
        collection_id: int,
        placements: list[dict],
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        seen: set[tuple[str, str]] = set()
        for placement in placements:
            surface = str(placement["surface_key"]).strip().lower()
            slot = str(placement["slot_key"]).strip().lower()
            if not KEY_PATTERN.fullmatch(surface) or not KEY_PATTERN.fullmatch(slot):
                raise HTTPException(
                    status_code=400,
                    detail="Ключи поверхности и слота могут содержать a-z, 0-9, '-' и '_'.",
                )
            key = (surface, slot)
            if key in seen:
                raise HTTPException(
                    status_code=400,
                    detail=f"Размещение {surface}.{slot} указано дважды.",
                )
            seen.add(key)
            placement["surface_key"] = surface
            placement["slot_key"] = slot
        await ProductCollectionDAO.replace_placements(
            session,
            collection_id=collection_id,
            placements=placements,
        )
        collection.updated_at = utc_now()
        session.add(collection)
        await session.commit()
        return await ManagerProductCollectionService.get_collection(session, collection_id)

    @staticmethod
    async def preview(
        session: AsyncSession,
        *,
        collection_id: int,
        surface_key: str,
        slot_key: str,
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        return await ProductCollectionResolver.resolve(
            session,
            collection=collection,
            surface_key=surface_key,
            slot_key=slot_key,
            enforce_publication=False,
        )

    @staticmethod
    async def archive(
        session: AsyncSession,
        collection_id: int,
    ) -> dict:
        collection = await ProductCollectionDAO.get(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        collection.status = "archived"
        collection.updated_at = utc_now()
        session.add(collection)
        await session.commit()
        return await ManagerProductCollectionService.get_collection(session, collection_id)

    @staticmethod
    async def duplicate(
        session: AsyncSession,
        collection_id: int,
    ) -> dict:
        source = await ProductCollectionDAO.get(session, collection_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        slug = await ManagerProductCollectionService._unique_slug(
            session,
            requested=f"{source.slug}-copy",
            fallback=f"{source.internal_name}-copy",
        )
        duplicate = ProductCollection(
            slug=slug,
            internal_name=f"{source.internal_name} — копия",
            public_title=source.public_title,
            public_description=source.public_description,
            public_badge=source.public_badge,
            cta_label=source.cta_label,
            cta_url=source.cta_url,
            editorial_note=source.editorial_note,
            status="draft",
            mode="manual",
            min_items=source.min_items,
            max_items=source.max_items,
            fallback_collection_id=source.fallback_collection_id,
        )
        session.add(duplicate)
        await session.flush()
        await ProductCollectionDAO.replace_items(
            session,
            collection_id=int(duplicate.id),
            items=[
                {
                    "product_id": item.product_id,
                    "is_pinned": item.is_pinned,
                    "editorial_note": item.editorial_note,
                }
                for item in sorted(source.items, key=lambda row: (row.position, row.id))
            ],
        )
        await session.commit()
        return await ManagerProductCollectionService.get_collection(
            session,
            int(duplicate.id),
        )

    @staticmethod
    def _serialize(collection: ProductCollection) -> dict:
        return {
            "id": int(collection.id),
            "slug": collection.slug,
            "internal_name": collection.internal_name,
            "public_title": collection.public_title,
            "public_description": collection.public_description,
            "public_badge": collection.public_badge,
            "cta_label": collection.cta_label,
            "cta_url": collection.cta_url,
            "editorial_note": collection.editorial_note,
            "status": collection.status,
            "mode": collection.mode,
            "min_items": collection.min_items,
            "max_items": collection.max_items,
            "fallback_collection_id": collection.fallback_collection_id,
            "starts_at": collection.starts_at,
            "ends_at": collection.ends_at,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
            "items": [
                {
                    "id": int(item.id),
                    "product_id": int(item.product_id),
                    "position": item.position,
                    "is_pinned": item.is_pinned,
                    "editorial_note": item.editorial_note,
                    "product_title": item.product.title,
                    "product_slug": item.product.slug,
                    "product_kind": item.product.product_kind,
                    "is_published": item.product.is_published,
                    "price": item.product.price,
                    "main_image": item.product.main_image,
                }
                for item in sorted(collection.items, key=lambda row: (row.position, row.id))
            ],
            "placements": [
                {
                    "id": int(placement.id),
                    "surface_key": placement.surface_key,
                    "slot_key": placement.slot_key,
                    "position": placement.position,
                    "is_enabled": placement.is_enabled,
                    "starts_at": placement.starts_at,
                    "ends_at": placement.ends_at,
                }
                for placement in sorted(
                    collection.placements,
                    key=lambda row: (
                        row.surface_key,
                        row.slot_key,
                        row.position,
                        row.id,
                    ),
                )
            ],
        }

    @staticmethod
    def _clean_fields(payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        for field in (
            "slug",
            "internal_name",
            "public_title",
            "public_description",
            "public_badge",
            "cta_label",
            "cta_url",
            "editorial_note",
        ):
            if field in data and data[field] is not None:
                value = str(data[field]).strip()
                data[field] = value or None
        return data

    @staticmethod
    def _validate_required_text(data: dict[str, Any]) -> None:
        for field, label in (
            ("internal_name", "Служебное название"),
            ("public_title", "Публичный заголовок"),
        ):
            if field in data and not data[field]:
                raise HTTPException(status_code=400, detail=f"{label} не может быть пустым.")

    @staticmethod
    async def _unique_slug(
        session: AsyncSession,
        *,
        requested: str | None,
        fallback: str,
        exclude_id: int | None = None,
    ) -> str:
        base = slugify(str(requested or fallback), lowercase=True)
        if not base:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug.")
        candidate = base
        suffix = 2
        while True:
            existing = await ProductCollectionDAO.get_by_slug(session, candidate)
            if existing is None or int(existing.id) == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    @staticmethod
    async def _validate_fallback(
        session: AsyncSession,
        *,
        fallback_id: int | None,
    ) -> None:
        if fallback_id is None:
            return
        if await ProductCollectionDAO.get(session, int(fallback_id)) is None:
            raise HTTPException(status_code=400, detail="Резервная подборка не найдена.")
