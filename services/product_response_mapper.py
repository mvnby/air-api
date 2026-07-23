"""Helpers to map Product domain models into public API DTOs."""

from typing import Any, Dict, List, Optional

from core.input_validation import validate_public_manual_url
from models import Product
from schemas import (
    ProductImageResponse,
    ProductManualResponse,
    ProductBrandResponse,
    ProductResponse,
    ProductSiblingResponse,
    TagGroupResponse,
    TagResponse,
)
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_series_payloads import build_product_series_response
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


def _ready_original_variant_url(image: Any) -> Optional[str]:
    for variant in getattr(image, "variants", None) or []:
        if (
            variant.variant_type == ProductImageVariantType.ORIGINAL.value
            and variant.processing_status == ProductImageProcessingStatus.READY.value
            and variant.url
        ):
            return variant.url
    return None


def _public_image_url(image: Any) -> Optional[str]:
    return _ready_original_variant_url(image) or image.url


def _public_image_url_map(product: Product) -> Dict[str, str]:
    url_map = {}
    for image in product.gallery_images or []:
        public_url = _public_image_url(image)
        source_url = getattr(image, "url", None)
        if not source_url or not public_url:
            continue
        url_map[source_url] = public_url
        url_map[source_url.strip("/")] = public_url
    return url_map


def _public_legacy_image_urls(product: Product, image_urls: List[str]) -> List[str]:
    url_map = _public_image_url_map(product)
    public_urls = []
    for url in image_urls:
        if not isinstance(url, str):
            public_urls.append(url)
            continue
        public_url = url_map.get(url) or url_map.get(url.strip("/"))
        if public_url:
            public_urls.append(public_url)
        elif not _is_legacy_product_media_url(url):
            public_urls.append(url)
    return public_urls


def _is_legacy_product_media_url(url: str) -> bool:
    return url.strip().lstrip("/").startswith("media/products/")


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

    return (
        _approved_ready_variant_url(source_image, variant_type)
        or _ready_original_variant_url(source_image)
        or product.main_image
    )


def _main_image_public_url(product: Product) -> Optional[str]:
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

    return _ready_original_variant_url(source_image) or product.main_image


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
                    url=_public_image_url(img),
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
            specs=sanitize_specs(item.specs),
            is_inverter=item.is_inverter,
            main_image=item.main_image,
        )
        for item in (series_siblings or [])
    ]

    series = product.series if product.series_id else None
    series_payload = build_product_series_response(series)

    manuals_payload = []
    for item in (product.attachments or []):
        if item.kind != "manual":
            continue
        try:
            public_url = validate_public_manual_url(item.url)
        except ValueError:
            continue
        manuals_payload.append(
            ProductManualResponse(
                id=item.id,
                kind=item.kind,
                title=item.title,
                url=public_url,
                source=item.source,
            )
        )

    availability_status = (supply_metrics or {}).get("availability_status")
    stock_state_map = {
        "in_stock_now": ("local_stock", 0, 0),
        "available_2_3_days": ("supplier_stock", 2, 3),
        "check_availability": ("available_to_order", None, None),
        "out_of_stock": ("out_of_stock", None, None),
    }
    public_stock_state, delivery_min_days, delivery_max_days = stock_state_map.get(
        availability_status,
        ("out_of_stock", None, None),
    )

    return ProductResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        price=product.price,
        old_price=product.old_price,
        product_kind=product.product_kind,
        is_inverter=product.is_inverter,
        power_cooling=product.power_cooling,
        main_image=_main_image_public_url(product),
        card_image=_main_image_variant_or_fallback(product, ProductImageVariantType.CARD),
        full_image=_main_image_variant_or_fallback(product, ProductImageVariantType.FULL),
        is_published=product.is_published,
        created_at=product.created_at,
        vitebsk_qty=int((supply_metrics or {}).get("vitebsk_qty", 0) or 0),
        minsk_qty=int((supply_metrics or {}).get("minsk_qty", 0) or 0),
        availability_status=availability_status,
        public_stock_state=public_stock_state,
        delivery_min_days=delivery_min_days,
        delivery_max_days=delivery_max_days,
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
        images=_public_legacy_image_urls(product, images or []),
        gallery_images=gallery,
        manuals=manuals_payload,
        series_siblings=siblings_payload,
        features=list(getattr(product, "__dict__", {}).get("_resolved_features") or []),
    )
