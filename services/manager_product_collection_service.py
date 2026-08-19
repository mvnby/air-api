from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_collection import ProductCollectionDAO
from core.request_context import current_request_id
from models import ProductCollection, TenantAuditEvent
from models.tenancy import TenantScope
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.product_collection_invalidation import ProductCollectionInvalidationService
from services.manager_product_collection_presenter import ManagerProductCollectionPresenter
from services.manager_product_collection_validation import (
    ManagerProductCollectionValidation,
)
from services.product_collection_resolver import ProductCollectionResolver
from services.product_collection_rule_policy import ProductCollectionRulePolicy


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _audit_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_audit_json_value(item) for item in value]
    return value


class ManagerProductCollectionService:
    @staticmethod
    async def search_products(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        search: str,
        limit: int,
    ) -> dict:
        projections = await ProductCollectionCatalogAccess.search_visible(
            session,
            tenant_scope=tenant_scope,
            search=search,
            limit=limit,
        )
        return {
            "items": [
                {
                    "id": int(projection.product.id),
                    "title": projection.product.title,
                    "slug": projection.product.slug,
                    "product_kind": projection.product.product_kind,
                    "is_published": bool(projection.product.is_published),
                    "price": projection.price,
                    "main_image": projection.product.main_image,
                }
                for projection in projections
            ]
        }

    @staticmethod
    async def get_rule_options(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict:
        allowed_product_ids = await ProductCollectionCatalogAccess.visible_product_ids(
            session,
            tenant_scope=tenant_scope,
        )
        rows = await ProductCollectionDAO.list_rule_option_rows(
            session,
            tenant_scope=tenant_scope,
            allowed_product_ids=allowed_product_ids,
        )
        return {
            "brands": [
                {"id": int(item.id), "label": item.title}
                for item in rows["brands"]
            ],
            "series": [
                {
                    "id": int(item.id),
                    "label": item.title,
                    "parent_id": int(item.brand_id),
                }
                for item in rows["series"]
            ],
            "features": [
                {"id": int(item.id), "label": item.name}
                for item in rows["features"]
            ],
        }

    @staticmethod
    async def list_collections(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[dict]:
        rows = await ProductCollectionDAO.list_all(
            session,
            tenant_scope=tenant_scope,
        )
        return await ManagerProductCollectionPresenter.serialize_many(
            session,
            rows,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def get_collection(
        session: AsyncSession,
        collection_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        return (
            await ManagerProductCollectionPresenter.serialize_many(
                session,
                [collection],
                tenant_scope=tenant_scope,
            )
        )[0]

    @staticmethod
    async def create_collection(
        session: AsyncSession,
        payload: dict[str, Any],
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        data = ManagerProductCollectionValidation.clean_fields(payload)
        ManagerProductCollectionValidation.required_text(data)
        ProductCollectionRulePolicy.validate_write(
            rule_config=data.get("rule_config") or {},
            tenant_scope=tenant_scope,
        )
        ManagerProductCollectionValidation.automation(
            mode=data.get("mode", "manual"),
            rule_config=data.get("rule_config") or {},
        )
        data["slug"] = await ManagerProductCollectionValidation.unique_slug(
            session,
            requested=data.get("slug"),
            fallback=data["internal_name"],
            tenant_scope=tenant_scope,
        )
        await ManagerProductCollectionValidation.fallback(
            session,
            fallback_id=data.get("fallback_collection_id"),
            tenant_scope=tenant_scope,
        )
        collection = ProductCollection(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            **data,
        )
        session.add(collection)
        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.created",
            change_set={"slug": {"before": None, "after": collection.slug}},
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            int(collection.id),
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_collection(
        session: AsyncSession,
        collection_id: int,
        payload: dict[str, Any],
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
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
        ManagerProductCollectionValidation.automation(
            mode=data.get("mode", collection.mode),
            rule_config=data.get("rule_config", collection.rule_config) or {},
        )

        change_set: dict[str, dict[str, Any]] = {}
        for field, value in data.items():
            before = getattr(collection, field)
            if before != value:
                change_set[field] = {"before": before, "after": value}
            setattr(collection, field, value)
        if not change_set:
            return await ManagerProductCollectionService.get_collection(
                session,
                collection_id,
                tenant_scope=tenant_scope,
            )
        collection.updated_at = utc_now()
        session.add(collection)
        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.updated",
            change_set=change_set,
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def replace_items(
        session: AsyncSession,
        collection_id: int,
        items: list[dict],
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
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
        before_ids = [
            int(item.product_id)
            for item in sorted(collection.items, key=lambda row: (row.position, row.id))
        ]
        async def stage_items() -> None:
            await ProductCollectionDAO.replace_items(
                session,
                collection_id=collection_id,
                tenant_scope=tenant_scope,
                items=items,
            )

        collection.updated_at = utc_now()
        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.items_reordered",
            change_set={"product_ids": {"before": before_ids, "after": product_ids}},
            stage_changes=stage_items,
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def replace_placements(
        session: AsyncSession,
        collection_id: int,
        placements: list[dict],
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
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
        before_placements = [
            {
                "surface_key": row.surface_key,
                "slot_key": row.slot_key,
                "position": row.position,
                "is_enabled": row.is_enabled,
            }
            for row in sorted(collection.placements, key=lambda row: (row.position, row.id))
        ]
        async def stage_placements() -> None:
            await ProductCollectionDAO.replace_placements(
                session,
                collection_id=collection_id,
                tenant_scope=tenant_scope,
                placements=placements,
            )

        collection.updated_at = utc_now()
        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.placements_reordered",
            change_set={
                "placements": {
                    "before": before_placements,
                    "after": placements,
                }
            },
            stage_changes=stage_placements,
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def preview(
        session: AsyncSession,
        *,
        collection_id: int,
        surface_key: str,
        slot_key: str,
        tenant_scope: TenantScope,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        return await ProductCollectionResolver.resolve(
            session,
            collection=collection,
            surface_key=surface_key,
            slot_key=slot_key,
            enforce_publication=False,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def archive(
        session: AsyncSession,
        collection_id: int,
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        collection = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        before_status = collection.status
        collection.status = "archived"
        collection.updated_at = utc_now()
        session.add(collection)
        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.archived",
            change_set={"status": {"before": before_status, "after": "archived"}},
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            collection_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def duplicate(
        session: AsyncSession,
        collection_id: int,
        *,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        source = await ProductCollectionDAO.get(
            session,
            collection_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Подборка не найдена.")
        slug = await ManagerProductCollectionValidation.unique_slug(
            session,
            requested=f"{source.slug}-copy",
            fallback=f"{source.internal_name}-copy",
            tenant_scope=tenant_scope,
        )
        duplicate = ProductCollection(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            slug=slug,
            internal_name=f"{source.internal_name} — копия",
            public_title=source.public_title,
            public_description=source.public_description,
            public_badge=source.public_badge,
            cta_label=source.cta_label,
            cta_url=source.cta_url,
            editorial_note=source.editorial_note,
            status="draft",
            mode=source.mode,
            sort_mode=source.sort_mode,
            rule_config=ProductCollectionRulePolicy.project_for_manager(
                dict(source.rule_config or {}),
                tenant_scope=tenant_scope,
            ),
            min_items=source.min_items,
            max_items=source.max_items,
            fallback_collection_id=source.fallback_collection_id,
        )
        session.add(duplicate)

        async def stage_duplicate_items() -> None:
            await session.flush()
            source_projections = await ProductCollectionCatalogAccess.visible_by_ids(
                session,
                tenant_scope=tenant_scope,
                product_ids=[int(item.product_id) for item in source.items],
            )
            await ProductCollectionDAO.replace_items(
                session,
                collection_id=int(duplicate.id),
                tenant_scope=tenant_scope,
                items=[
                    {
                        "product_id": item.product_id,
                        "is_pinned": item.is_pinned,
                        "editorial_note": item.editorial_note,
                    }
                    for item in sorted(source.items, key=lambda row: (row.position, row.id))
                    if int(item.product_id) in source_projections
                ],
            )

        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=duplicate,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.duplicated",
            change_set={
                "source_collection_id": {
                    "before": None,
                    "after": int(source.id),
                }
            },
            stage_changes=stage_duplicate_items,
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            int(duplicate.id),
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def _stage_mutation(
        session: AsyncSession,
        *,
        collection: ProductCollection,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        action: str,
        change_set: dict[str, Any],
    ) -> None:
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                actor_staff_user_id=actor_staff_user_id,
                actor_username=actor_username,
                action=action,
                entity_type="product_collection",
                entity_id=int(collection.id),
                request_id=current_request_id(),
                change_set=_audit_json_value(change_set),
            )
        )
        await ProductCollectionInvalidationService.stage(
            session,
            tenant_scope=tenant_scope,
            reason=action.replace(".", "_"),
        )
        await session.flush()

    @staticmethod
    async def _commit_mutation(
        session: AsyncSession,
        *,
        collection: ProductCollection,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        action: str,
        change_set: dict[str, Any],
        stage_changes: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        try:
            if stage_changes is not None:
                await stage_changes()
            await session.flush()
            await ManagerProductCollectionService._stage_mutation(
                session,
                collection=collection,
                tenant_scope=tenant_scope,
                actor_username=actor_username,
                actor_staff_user_id=actor_staff_user_id,
                action=action,
                change_set=change_set,
            )
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Подборка была изменена параллельно. Повторите запрос.",
            ) from exc
        except Exception:
            await session.rollback()
            raise
