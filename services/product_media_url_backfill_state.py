"""Load, snapshot, inspect, and mutate exact product-media URL locations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ProductImage, ProductImageVariant
from services.product_media_url_backfill_manifest import (
    ProductMediaUrlBackfillManifest,
)
from services.product_media_url_backfill_plan_token import (
    ProductMediaUrlBackfillBlockedError,
)


@dataclass(slots=True)
class LoadedProductMediaUrlState:
    products: list[Product]
    products_by_id: dict[int, Product]
    image_by_id: dict[int, ProductImage]
    variant_by_id: dict[int, ProductImageVariant]


async def load_product_media_url_state(
    session: AsyncSession,
    *,
    for_update: bool,
) -> LoadedProductMediaUrlState:
    stmt = (
        select(Product)
        .where(Product.is_published.is_(True))
        .options(
            selectinload(Product.gallery_images).selectinload(ProductImage.variants)
        )
        .order_by(Product.id.asc())
    )
    if for_update:
        stmt = stmt.with_for_update()
    products = list((await session.execute(stmt)).scalars().unique().all())
    if for_update:
        product_ids = [int(product.id) for product in products]
        if product_ids:
            list(
                (
                    await session.execute(
                        select(ProductImage)
                        .where(ProductImage.product_id.in_(product_ids))
                        .options(selectinload(ProductImage.variants))
                        .order_by(ProductImage.id.asc())
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).scalars()
            )
            image_ids = [
                int(image.id)
                for product in products
                for image in product.gallery_images or []
                if image.id is not None
            ]
            if image_ids:
                list(
                    (
                        await session.execute(
                            select(ProductImageVariant)
                            .where(
                                ProductImageVariant.product_image_id.in_(image_ids)
                            )
                            .order_by(ProductImageVariant.id.asc())
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).scalars()
                )
    images = {
        int(image.id): image
        for product in products
        for image in product.gallery_images or []
        if image.id is not None
    }
    variants = {
        int(variant.id): variant
        for image in images.values()
        for variant in image.variants or []
        if variant.id is not None
    }
    return LoadedProductMediaUrlState(
        products=products,
        products_by_id={int(product.id): product for product in products},
        image_by_id=images,
        variant_by_id=variants,
    )


def product_media_url_db_snapshot_hash(products: list[Product]) -> str:
    payload = [
        {
            "id": int(product.id),
            "slug": str(product.slug),
            "main_image": product.main_image,
        }
        for product in products
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def collect_product_media_url_locations(
    state: LoadedProductMediaUrlState,
    manifest: ProductMediaUrlBackfillManifest,
) -> list[dict[str, Any]]:
    source_by_product_id = {
        product_id: source.old_url
        for source in manifest.sources
        if source.action != "blocked"
        for product_id in source.expected_product_ids
    }
    locations: list[dict[str, Any]] = []
    for product in state.products:
        product_id = int(product.id)
        source_url = source_by_product_id.get(product_id)
        if source_url is None:
            continue
        if product.main_image == source_url:
            locations.append(
                _location(
                    "product",
                    product_id,
                    product_id,
                    "main_image",
                    None,
                    product.main_image,
                )
            )
        for index, value in enumerate(list(product.images or [])):
            if value == source_url:
                locations.append(
                    _location(
                        "product", product_id, product_id, "images", index, value
                    )
                )
        for image in product.gallery_images or []:
            if image.url == source_url:
                locations.append(
                    _location(
                        "product_image",
                        int(image.id),
                        product_id,
                        "url",
                        None,
                        image.url,
                    )
                )
            for variant in image.variants or []:
                if variant.url == source_url:
                    locations.append(
                        _location(
                            "product_image_variant",
                            int(variant.id),
                            product_id,
                            "url",
                            None,
                            variant.url,
                        )
                    )
    return sorted(
        locations,
        key=lambda item: (
            item["product_id"],
            item["table"],
            item["row_id"],
            item["field"],
            -1 if item["index"] is None else item["index"],
        ),
    )


def detect_product_media_url_collisions(
    state: LoadedProductMediaUrlState,
    manifest: ProductMediaUrlBackfillManifest,
    target_by_source: dict[str, str | None],
    blockers: list[str],
) -> None:
    for source in manifest.sources:
        if source.action == "blocked":
            continue
        target = target_by_source.get(source.old_url)
        if not target or target == source.old_url:
            continue
        for product_id in source.expected_product_ids:
            product = state.products_by_id.get(product_id)
            if product is None:
                continue
            image_urls = [image.url for image in product.gallery_images or []]
            if source.old_url in image_urls and target in image_urls:
                blockers.append(
                    f"product#{product_id} already has ProductImage target {target}"
                )


def product_media_url_targets_are_complete(
    state: LoadedProductMediaUrlState,
    manifest: ProductMediaUrlBackfillManifest,
    target_by_source: dict[str, str | None],
) -> bool:
    for source in manifest.sources:
        if source.action == "blocked":
            continue
        target = target_by_source.get(source.old_url)
        if not target:
            return False
        for product_id in source.expected_product_ids:
            product = state.products_by_id.get(product_id)
            if product is None or product.main_image != target:
                return False
    return True


def apply_product_media_url_locations(
    state: LoadedProductMediaUrlState,
    *,
    locations: list[dict[str, Any]],
    target_by_source: dict[str, str],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for location in locations:
        before = location["old_url"]
        target = target_by_source.get(before)
        if not target:
            raise ProductMediaUrlBackfillBlockedError(
                "Reviewed target is missing for a planned location"
            )
        table = location["table"]
        row_id = int(location["row_id"])
        if table == "product":
            row = state.products_by_id[row_id]
            if location["field"] == "main_image":
                if row.main_image != before:
                    raise ProductMediaUrlBackfillBlockedError(
                        "Product main image changed after planning"
                    )
                row.main_image = target
            else:
                values = list(row.images or [])
                index = int(location["index"])
                if index >= len(values) or values[index] != before:
                    raise ProductMediaUrlBackfillBlockedError(
                        "Product image list changed after planning"
                    )
                values[index] = target
                row.images = values
        elif table == "product_image":
            row = state.image_by_id[row_id]
            if row.url != before:
                raise ProductMediaUrlBackfillBlockedError(
                    "ProductImage changed after planning"
                )
            row.url = target
        else:
            row = state.variant_by_id[row_id]
            if row.url != before:
                raise ProductMediaUrlBackfillBlockedError(
                    "ProductImageVariant changed after planning"
                )
            row.url = target
        changes.append({**location, "new_url": target})
    return changes


def _location(
    table: str,
    row_id: int,
    product_id: int,
    field: str,
    index: int | None,
    old_url: str,
) -> dict[str, Any]:
    return {
        "table": table,
        "row_id": row_id,
        "product_id": product_id,
        "field": field,
        "index": index,
        "old_url": old_url,
    }


__all__ = [
    "LoadedProductMediaUrlState",
    "apply_product_media_url_locations",
    "collect_product_media_url_locations",
    "detect_product_media_url_collisions",
    "load_product_media_url_state",
    "product_media_url_db_snapshot_hash",
    "product_media_url_targets_are_complete",
]
