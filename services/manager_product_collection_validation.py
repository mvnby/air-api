from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_collection import ProductCollectionDAO
from models.tenancy import TenantScope


KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class ManagerProductCollectionValidation:
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
