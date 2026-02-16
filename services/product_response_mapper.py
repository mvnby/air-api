"""Helpers to map Product domain models into public API DTOs."""

from typing import List, Optional

from models import Product
from schemas import (
    ProductImageResponse,
    ProductResponse,
    ProductSiblingResponse,
    TagGroupResponse,
    TagResponse,
)
from services.product_serialization import parse_legacy_images, sanitize_specs


def map_product_to_response(
    product: Product,
    series_siblings: Optional[List[Product]] = None,
) -> ProductResponse:
    tags_payload = []
    if product.tags:
        for tag in product.tags:
            group = None
            if tag.group:
                group = TagGroupResponse(
                    title=tag.group.title,
                    slug=tag.group.slug,
                    is_public=tag.group.is_public,
                )
            tags_payload.append(
                TagResponse(
                    id=tag.id,
                    title=tag.title,
                    slug=tag.slug,
                    is_public=tag.is_public,
                    sort_order=tag.sort_order,
                    group=group,
                    group_title=tag.group.title if tag.group else None,
                )
            )

    specs = sanitize_specs(product.specs)
    images = parse_legacy_images(product.images)

    gallery = []
    if product.gallery_images:
        for img in product.gallery_images:
            gallery.append(
                ProductImageResponse(
                    id=img.id,
                    url=img.url,
                    is_installation_photo=img.is_installation_photo,
                )
            )

    siblings_payload = [
        ProductSiblingResponse(
            id=item.id,
            title=item.title,
            slug=item.slug,
            price=item.price,
            old_price=item.old_price,
            area=item.area,
            is_inverter=item.is_inverter,
            main_image=item.main_image,
        )
        for item in (series_siblings or [])
    ]

    return ProductResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        price=product.price,
        old_price=product.old_price,
        area=product.area,
        is_inverter=product.is_inverter,
        power_cooling=product.power_cooling,
        main_image=product.main_image,
        is_published=product.is_published,
        created_at=product.created_at,
        tags=tags_payload,
        specs=specs or {},
        images=images or [],
        gallery_images=gallery,
        series_siblings=siblings_payload,
    )
