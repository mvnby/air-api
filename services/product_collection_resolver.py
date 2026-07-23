from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from crud.product import ProductDAO
from crud.product_collection import ProductCollectionDAO
from models import ProductCollection
from services.feature_resolver_service import FeatureResolverService
from services.product_collection_eligibility import ProductCollectionEligibility
from services.product_read_service import ProductReadService
from services.product_response_mapper import map_product_to_response


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_active_window(
    *,
    starts_at: datetime | None,
    ends_at: datetime | None,
    now: datetime,
) -> bool:
    if starts_at is not None and starts_at > now:
        return False
    return ends_at is None or ends_at > now


class ProductCollectionResolver:
    @staticmethod
    async def resolve(
        session: AsyncSession,
        *,
        collection: ProductCollection,
        surface_key: str,
        slot_key: str,
        enforce_publication: bool,
        selection_source: str = "manual",
        visited_collection_ids: set[int] | None = None,
    ) -> dict:
        now = utc_now()
        if enforce_publication and (
            collection.status != "published"
            or not _is_active_window(
                starts_at=collection.starts_at,
                ends_at=collection.ends_at,
                now=now,
            )
        ):
            return ProductCollectionResolver._empty_result(collection)

        visited = set(visited_collection_ids or set())
        collection_id = int(collection.id)
        if collection_id in visited:
            return ProductCollectionResolver._empty_result(collection)
        visited.add(collection_id)

        item_rows = await ProductCollectionDAO.list_items(session, collection_id)
        product_ids = [int(item.product_id) for item in item_rows]
        products = await ProductDAO.get_by_ids(
            session,
            product_ids,
            load_image_variants=True,
        )
        product_map = {int(product.id): product for product in products}
        if products:
            await FeatureResolverService.resolve_for_products(session, products)
        supply_metrics = await ProductReadService.get_supply_metrics_map(session, products)

        selected: list[dict] = []
        excluded: list[dict] = []
        for item in item_rows:
            product = product_map.get(int(item.product_id))
            if product is None:
                excluded.append(
                    {
                        "product_id": int(item.product_id),
                        "product_title": f"Товар #{item.product_id}",
                        "position": int(item.position),
                        "reason_codes": ["product_missing"],
                        "reasons": ["Товар больше не существует."],
                    }
                )
                continue
            metrics = supply_metrics.get(int(product.id), {})
            eligibility = ProductCollectionEligibility.evaluate(
                product,
                surface_key=surface_key,
                slot_key=slot_key,
                supply_metrics=metrics,
            )
            if not eligibility.is_eligible:
                excluded.append(
                    {
                        "product_id": int(product.id),
                        "product_title": product.title,
                        "position": int(item.position),
                        "reason_codes": list(eligibility.reason_codes),
                        "reasons": list(eligibility.reasons),
                    }
                )
                continue
            selected.append(
                {
                    "selection_source": selection_source,
                    "position": len(selected),
                    "product": map_product_to_response(
                        product,
                        supply_metrics=metrics,
                    ),
                }
            )
            if len(selected) >= collection.max_items:
                break

        below_min = len(selected) < collection.min_items
        if below_min and collection.fallback_collection_id:
            fallback = await ProductCollectionDAO.get(
                session,
                int(collection.fallback_collection_id),
            )
            if fallback is not None:
                fallback_result = await ProductCollectionResolver.resolve(
                    session,
                    collection=fallback,
                    surface_key=surface_key,
                    slot_key=slot_key,
                    enforce_publication=enforce_publication,
                    selection_source="fallback",
                    visited_collection_ids=visited,
                )
                if not fallback_result["below_min_items"]:
                    return {
                        "collection_id": collection_id,
                        "collection_slug": collection.slug,
                        "below_min_items": False,
                        "fallback_used": True,
                        "items": fallback_result["items"][: collection.max_items],
                        "excluded_items": excluded + fallback_result["excluded_items"],
                    }

        return {
            "collection_id": collection_id,
            "collection_slug": collection.slug,
            "below_min_items": below_min,
            "fallback_used": False,
            "items": selected,
            "excluded_items": excluded,
        }

    @staticmethod
    def _empty_result(collection: ProductCollection) -> dict:
        return {
            "collection_id": int(collection.id),
            "collection_slug": collection.slug,
            "below_min_items": True,
            "fallback_used": False,
            "items": [],
            "excluded_items": [],
        }

    @staticmethod
    async def resolve_placement(
        session: AsyncSession,
        *,
        surface_key: str,
        slot_key: str,
    ) -> dict:
        rows = await ProductCollectionDAO.list_placements(
            session,
            surface_key=surface_key,
            slot_key=slot_key,
            now=utc_now(),
        )
        if surface_key == "home" and slot_key == "featured_products":
            rows = rows[:4]

        collections: list[dict] = []
        for placement, collection in rows:
            resolved = await ProductCollectionResolver.resolve(
                session,
                collection=collection,
                surface_key=surface_key,
                slot_key=slot_key,
                enforce_publication=True,
            )
            if resolved["below_min_items"]:
                continue
            collections.append(
                {
                    "slug": collection.slug,
                    "title": collection.public_title,
                    "description": collection.public_description,
                    "badge": collection.public_badge,
                    "cta_label": collection.cta_label,
                    "cta_url": collection.cta_url,
                    "position": int(placement.position),
                    "updated_at": collection.updated_at,
                    "items": resolved["items"],
                }
            )
        return {
            "surface": surface_key,
            "slot": slot_key,
            "collections": collections,
        }
