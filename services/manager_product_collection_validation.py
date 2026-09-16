from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from api_contracts.product_collections import ProductCollectionFields
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_collection import ProductCollectionDAO
from models import ProductCollection
from models.tenancy import TenantScope
from services.product_collection_rule_policy import ProductCollectionRulePolicy
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class ManagerProductCollectionValidation:
    @staticmethod
    async def update_fields(session: AsyncSession, collection: ProductCollection, payload: dict[str, Any], *, tenant_scope: TenantScope) -> dict[str, Any]:
        collection_id = int(collection.id)
        data = ManagerProductCollectionValidation.clean_fields(payload)
        ManagerProductCollectionValidation.required_text(data)
        if "rule_config" in data:
            ProductCollectionRulePolicy.validate_write(
                rule_config=data.get("rule_config") or {},
                tenant_scope=tenant_scope,
            )
        if "slug" in data:
            data["slug"] = await ManagerProductCollectionValidation.unique_slug(
                session,
                requested=data["slug"],
                fallback=data.get("internal_name") or collection.internal_name,
                exclude_id=collection_id,
                tenant_scope=tenant_scope,
            )
        fallback_id = data.get("fallback_collection_id")
        if fallback_id == collection_id:
            raise HTTPException(status_code=400, detail="Подборка не может ссылаться сама на себя.")
        if "fallback_collection_id" in data:
            await ManagerProductCollectionValidation.fallback(
                session,
                fallback_id=fallback_id,
                tenant_scope=tenant_scope,
            )

        try:
            ProductCollectionFields.model_validate({
                field: data.get(field, getattr(collection, field))
                for field in ProductCollectionFields.model_fields
            })
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="Некорректные параметры подборки.") from exc
        ManagerProductCollectionValidation.automation(
            mode=data.get("mode", collection.mode),
            rule_config=data.get("rule_config", collection.rule_config) or {},
        )

        return data

    @staticmethod
    async def items(session: AsyncSession, items: list[dict], *, tenant_scope: TenantScope) -> list[int]:
        product_ids = [int(item["product_id"]) for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise HTTPException(status_code=400, detail="Один товар нельзя добавить дважды.")
        projections = await ProductCollectionCatalogAccess.visible_by_ids(
            session,
            tenant_scope=tenant_scope,
            product_ids=product_ids,
        )
        if len(projections) != len(product_ids):
            found_ids = set(projections)
            missing = [product_id for product_id in product_ids if product_id not in found_ids]
            raise HTTPException(
                status_code=404,
                detail=f"Товары недоступны для этой витрины: {', '.join(map(str, missing))}.",
            )
        return product_ids

    @staticmethod
    def placements(placements: list[dict]) -> None:
        seen: set[tuple[str, str]] = set()
        for placement in placements:
            surface = ManagerProductCollectionValidation.placement_key(
                placement["surface_key"]
            )
            slot = ManagerProductCollectionValidation.placement_key(
                placement["slot_key"]
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

    @staticmethod
    def clean_fields(payload: dict[str, Any]) -> dict[str, Any]:
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
    def required_text(data: dict[str, Any]) -> None:
        for field, label in (
            ("internal_name", "Служебное название"),
            ("public_title", "Публичный заголовок"),
        ):
            if field in data and not data[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"{label} не может быть пустым.",
                )

    @staticmethod
    def automation(*, mode: str, rule_config: dict[str, Any]) -> None:
        if mode == "manual":
            return
        if not any(value not in (None, [], "") for value in rule_config.values()):
            raise HTTPException(
                status_code=400,
                detail="Для automatic/hybrid задайте хотя бы одно типизированное условие.",
            )

    @staticmethod
    def placement_key(value: Any) -> str:
        normalized = str(value).strip().lower()
        if not KEY_PATTERN.fullmatch(normalized):
            raise HTTPException(
                status_code=400,
                detail="Ключи поверхности и слота могут содержать a-z, 0-9, '-' и '_'.",
            )
        return normalized

    @staticmethod
    async def unique_slug(
        session: AsyncSession,
        *,
        requested: str | None,
        fallback: str,
        tenant_scope: TenantScope,
        exclude_id: int | None = None,
    ) -> str:
        base = slugify(str(requested or fallback), lowercase=True)
        if not base:
            raise HTTPException(status_code=400, detail="Не удалось сформировать slug.")
        candidate = base
        suffix = 2
        while True:
            existing = await ProductCollectionDAO.get_by_slug(
                session,
                candidate,
                tenant_scope=tenant_scope,
            )
            if existing is None or int(existing.id) == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    @staticmethod
    async def fallback(
        session: AsyncSession,
        *,
        fallback_id: int | None,
        tenant_scope: TenantScope,
    ) -> None:
        if fallback_id is None:
            return
        fallback = await ProductCollectionDAO.get(
            session,
            int(fallback_id),
            tenant_scope=tenant_scope,
        )
        if fallback is None:
            raise HTTPException(status_code=404, detail="Резервная подборка не найдена.")


__all__ = ["ManagerProductCollectionValidation"]
