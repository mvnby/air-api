import pytest

from models import Product, ProductImage, ProductImageVariant
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_response_mapper import map_product_to_response


def _product_with_variant(
    *,
    variant_type: ProductImageVariantType = ProductImageVariantType.CARD,
    processing_status: str = ProductImageProcessingStatus.READY.value,
    manual_quality_status: str = ProductImageManualQualityStatus.APPROVED.value,
    variant_url: str | None = "/media/products/variants/card/source.webp",
) -> Product:
    product = Product(
        id=1,
        title="Variant Product",
        slug="variant-product",
        description="",
        price=1200,
        area=25,
        main_image="/media/products/source.webp",
        is_published=True,
    )
    source_image = ProductImage(
        id=10,
        product_id=product.id,
        url="/media/products/source.webp",
        is_installation_photo=False,
    )
    source_image.variants = [
        ProductImageVariant(
            id=100,
            product_image_id=source_image.id,
            variant_type=variant_type.value,
            url=variant_url,
            processing_status=processing_status,
            manual_quality_status=manual_quality_status,
        )
    ]
    product.gallery_images = [source_image]
    return product


def test_map_product_to_response_selects_only_approved_ready_card_and_full_variants():
    product = _product_with_variant()
    product.gallery_images[0].variants.append(
        ProductImageVariant(
            id=101,
            product_image_id=product.gallery_images[0].id,
            variant_type=ProductImageVariantType.FULL.value,
            url="/media/products/variants/full/source.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
            manual_quality_status=ProductImageManualQualityStatus.APPROVED.value,
        )
    )

    payload = map_product_to_response(product)

    assert payload.main_image == "/media/products/source.webp"
    assert payload.card_image == "/media/products/variants/card/source.webp"
    assert payload.full_image == "/media/products/variants/full/source.webp"
    assert payload.gallery_images[0].url == "/media/products/source.webp"
    assert payload.gallery_images[0].card_variant_url == "/media/products/variants/card/source.webp"
    assert payload.gallery_images[0].full_variant_url == "/media/products/variants/full/source.webp"


@pytest.mark.parametrize(
    ("processing_status", "manual_quality_status", "variant_url"),
    [
        (ProductImageProcessingStatus.PROCESSING.value, ProductImageManualQualityStatus.APPROVED.value, "/card.webp"),
        (ProductImageProcessingStatus.FAILED.value, ProductImageManualQualityStatus.APPROVED.value, "/card.webp"),
        (ProductImageProcessingStatus.SKIPPED.value, ProductImageManualQualityStatus.APPROVED.value, "/card.webp"),
        (ProductImageProcessingStatus.READY.value, ProductImageManualQualityStatus.UNREVIEWED.value, "/card.webp"),
        (ProductImageProcessingStatus.READY.value, ProductImageManualQualityStatus.REJECTED.value, "/card.webp"),
        (ProductImageProcessingStatus.READY.value, ProductImageManualQualityStatus.APPROVED.value, None),
    ],
)
def test_map_product_to_response_falls_back_when_variant_is_not_public(
    processing_status,
    manual_quality_status,
    variant_url,
):
    product = _product_with_variant(
        processing_status=processing_status,
        manual_quality_status=manual_quality_status,
        variant_url=variant_url,
    )

    payload = map_product_to_response(product)

    assert payload.card_image == "/media/products/source.webp"
    assert payload.full_image == "/media/products/source.webp"
    assert payload.gallery_images[0].card_variant_url is None
    assert payload.gallery_images[0].full_variant_url is None


def test_map_product_to_response_keeps_legacy_product_without_variants_unchanged():
    product = Product(
        id=1,
        title="Legacy Product",
        slug="legacy-product",
        description="",
        price=1200,
        area=25,
        main_image="/media/products/legacy.webp",
        is_published=True,
    )
    product.gallery_images = [
        ProductImage(
            id=10,
            product_id=product.id,
            url="/media/products/legacy.webp",
            is_installation_photo=False,
        )
    ]

    payload = map_product_to_response(product)

    assert payload.main_image == "/media/products/legacy.webp"
    assert payload.card_image == "/media/products/legacy.webp"
    assert payload.full_image == "/media/products/legacy.webp"
    assert payload.gallery_images[0].url == "/media/products/legacy.webp"
    assert payload.gallery_images[0].card_variant_url is None
    assert payload.gallery_images[0].full_variant_url is None
