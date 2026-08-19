from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import ProductCollection
from models.tenancy import TenantScope
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


class ManagerProductCollectionPresenter:
    @classmethod
    async def serialize_many(
        cls,
        session: AsyncSession,
        collections: list[ProductCollection],
        *,
        tenant_scope: TenantScope,
    ) -> list[dict]:
        product_ids = {
            int(item.product_id)
            for collection in collections
            for item in collection.items
        }
        projections = await ProductCollectionCatalogAccess.visible_by_ids(
            session,
            tenant_scope=tenant_scope,
            product_ids=product_ids,
        )
        return [cls._serialize(collection, projections=projections) for collection in collections]

    @staticmethod
    def _serialize(collection: ProductCollection, *, projections: dict[int, Any]) -> dict:
        return {
            "id": int(collection.id),
            "tenant_id": collection.tenant_id,
            "storefront_id": collection.storefront_id,
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
            "sort_mode": collection.sort_mode,
            "rule_config": dict(collection.rule_config or {}),
            "min_items": collection.min_items,
            "max_items": collection.max_items,
            "fallback_collection_id": collection.fallback_collection_id,
            "starts_at": collection.starts_at,
            "ends_at": collection.ends_at,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
            "items": [
                ManagerProductCollectionPresenter._serialize_item(
                    item,
                    projection=projections[int(item.product_id)],
                )
                for item in sorted(collection.items, key=lambda row: (row.position, row.id))
                if int(item.product_id) in projections
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
    def _serialize_item(item, *, projection) -> dict:
        product = projection.product
        return {
            "id": int(item.id),
            "product_id": int(item.product_id),
            "position": item.position,
            "is_pinned": item.is_pinned,
            "editorial_note": item.editorial_note,
            "product_title": product.title,
            "product_slug": product.slug,
            "product_kind": product.product_kind,
            "is_published": product.is_published,
            "price": projection.price,
            "main_image": product.main_image,
        }


__all__ = ["ManagerProductCollectionPresenter"]
