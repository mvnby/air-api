"""Helpers to map Product domain models into public API DTOs."""

from typing import Any, Dict, List, Optional

from models import Product
from schemas import (
    ProductImageResponse,
    ProductManualResponse,
    ProductBrandResponse,
    ProductResponse,
    ProductSeriesResponse,
    ProductSiblingResponse,
    TagGroupResponse,
    TagResponse,
)
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_serialization import parse_legacy_images, sanitize_specs


def _is_same_image_url(left: Optional[str], right: Optional[str]) -> bool:
    if not left or not right:
        return False
    return left == right or left.strip("/") == right.strip("/")


def _approved_ready_variant_url(image: Any, variant_type: ProductImageVariantType) -> Optional[str]:
    for variant in getattr(image, "variants", None) or []:
        if (
            variant.variant_type == variant_type.value
            and variant.processing_status == ProductImageProcessingStatus.READY.value
            and variant.manual_quality_status == ProductImageManualQualityStatus.APPROVED.value
            and variant.url
        ):
            return variant.url
    return None


def _main_image_variant_or_fallback(
    product: Product,
    variant_type: ProductImageVariantType,
) -> Optional[str]:
    if not product.main_image:
        return None

    source_image = next(
        (
            image
            for image in (product.gallery_images or [])
            if _is_same_image_url(image.url, product.main_image)
        ),
        None,
    )
    if not source_image:
        return product.main_image

    return _approved_ready_variant_url(source_image, variant_type) or product.main_image


def map_product_to_response(
    product: Product,
    series_siblings: Optional[List[Product]] = None,
    supply_metrics: Optional[Dict[str, Any]] = None,
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
                    card_variant_url=_approved_ready_variant_url(
                        img,
                        ProductImageVariantType.CARD,
                    ),
                    full_variant_url=_approved_ready_variant_url(
                        img,
                        ProductImageVariantType.FULL,
                    ),
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

    series = product.series if product.series_id else None
    series_payload = (
        ProductSeriesResponse(
            id=series.id,
            title=series.title,
            slug=series.slug,
            description=series.description,
            hero_image=series.hero_image,
            features=series.features or [],
        )
        if series and series.is_published
        else None
    )

    manuals_payload = [
        ProductManualResponse(
            id=item.id,
            kind=item.kind,
            title=item.title,
            url=item.url,
            source=item.source,
        )
        for item in (product.attachments or [])
        if item.kind == "manual"
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
        card_image=_main_image_variant_or_fallback(product, ProductImageVariantType.CARD),
        full_image=_main_image_variant_or_fallback(product, ProductImageVariantType.FULL),
        is_published=product.is_published,
        created_at=product.created_at,
        vitebsk_qty=int((supply_metrics or {}).get("vitebsk_qty", 0) or 0),
        minsk_qty=int((supply_metrics or {}).get("minsk_qty", 0) or 0),
        availability_status=(supply_metrics or {}).get("availability_status"),
        brand=(
            ProductBrandResponse(
                id=product.brand.id,
                title=product.brand.title,
                slug=product.brand.slug,
                logo_url=product.brand.logo_url,
            )
            if product.brand
            else None
        ),
        series=series_payload,
        tags=tags_payload,
        specs=specs or {},
        images=images or [],
        gallery_images=gallery,
        manuals=manuals_payload,
        series_siblings=siblings_payload,
    )
