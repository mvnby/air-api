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
from services.public_catalog_visibility_service import PublicProductProjection
from services.public_taxonomy_service import PublicTaxonomyService


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
    projection: PublicProductProjection,
    series_siblings: Optional[List[PublicProductProjection]] = None,
    supply_metrics: Optional[Dict[str, Any]] = None,
) -> ProductResponse:
    product = projection.product
    tags_payload = []
    if product.tags:
        for tag in PublicTaxonomyService.visible_tags(product.tags):
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

    siblings_payload = []
    for sibling_projection in series_siblings or []:
        item = sibling_projection.product
        siblings_payload.append(
            ProductSiblingResponse(
                id=item.id,
                title=item.title,
                slug=item.slug,
                price=sibling_projection.price,
                old_price=sibling_projection.old_price,
                specs=sanitize_specs(item.specs),
                is_inverter=item.is_inverter,
                main_image=item.main_image,
            )
        )

    public_brand = PublicTaxonomyService.public_brand(product)
    series = PublicTaxonomyService.public_series(product)
    series_payload = build_product_series_response(
        series,
        disclosure_policy=projection.disclosure_policy,
    )

    manuals_payload = []
    for item in (product.attachments or []):
        if item.kind != "manual":
            continue
        try:
            public_url = validate_public_manual_url(item.url)
        except ValueError:
            continue
        manual_payload = ProductManualResponse(
            id=item.id,
            kind=item.kind,
            title=item.title,
            url=public_url,
            source=item.source,
        )
        manual_payload._disclose_source = (
            projection.disclosure_policy.expose_source_provenance
        )
        manuals_payload.append(manual_payload)

    availability = projection.disclosure_policy.project_availability(
        supply_metrics
    )

    response = ProductResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        price=projection.price,
        old_price=projection.old_price,
        product_kind=product.product_kind,
        is_inverter=product.is_inverter,
        power_cooling=product.power_cooling,
        main_image=_main_image_public_url(product),
        card_image=_main_image_variant_or_fallback(product, ProductImageVariantType.CARD),
        full_image=_main_image_variant_or_fallback(product, ProductImageVariantType.FULL),
        is_published=product.is_published,
        created_at=product.created_at,
        vitebsk_qty=availability.vitebsk_qty,
        minsk_qty=availability.minsk_qty,
        availability_status=availability.availability_status,
        public_stock_state=availability.public_stock_state,
        delivery_min_days=availability.delivery_min_days,
        delivery_max_days=availability.delivery_max_days,
        brand=(
            ProductBrandResponse(
                id=public_brand.id,
                title=public_brand.title,
                slug=public_brand.slug,
                logo_url=public_brand.logo_url,
            )
            if public_brand
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
    response._disclose_legacy_availability = (
        projection.disclosure_policy.expose_legacy_availability
    )
    return response
