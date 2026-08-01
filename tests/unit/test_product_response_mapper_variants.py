import pytest

from models import (
    Product,
    ProductImage,
    ProductImageVariant,
    ProductSeries,
    Tag,
    TagGroup,
)
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
        specs={"area_m2": 25},
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


def test_map_product_to_response_excludes_hidden_tags_and_hidden_groups():
    product = _product_with_variant()
    public_group = TagGroup(
        id=1,
        title="Public group",
        slug="public-group",
        is_public=True,
    )
    hidden_group = TagGroup(
        id=2,
        title="Internal group",
        slug="internal-group",
        is_public=False,
    )
    public_tag = Tag(
        id=10,
        group_id=1,
        title="Visible",
        slug="visible",
        is_public=True,
    )
    hidden_tag = Tag(
        id=11,
        group_id=1,
        title="Internal tag",
        slug="internal-tag",
        is_public=False,
    )
    tag_in_hidden_group = Tag(
        id=12,
        group_id=2,
        title="Internal group tag",
        slug="internal-group-tag",
        is_public=True,
    )
    public_tag.group = public_group
    hidden_tag.group = public_group
    tag_in_hidden_group.group = hidden_group
    product.tags = [public_tag, hidden_tag, tag_in_hidden_group]

    payload = map_product_to_response(product)

    assert [tag.slug for tag in payload.tags] == ["visible"]
    serialized = payload.model_dump_json()
    assert "Internal tag" not in serialized
    assert "Internal group" not in serialized


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


def test_map_product_to_response_uses_ready_original_variant_as_public_cdn_fallback():
    product = _product_with_variant(
        processing_status=ProductImageProcessingStatus.READY.value,
        manual_quality_status=ProductImageManualQualityStatus.UNREVIEWED.value,
        variant_url="/media/products/variants/card/unapproved.webp",
    )
    product.gallery_images[0].variants.append(
        ProductImageVariant(
            id=102,
            product_image_id=product.gallery_images[0].id,
            variant_type=ProductImageVariantType.ORIGINAL.value,
            url="https://cdn.mvn.by/products/variants/original/source.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
            manual_quality_status=ProductImageManualQualityStatus.UNREVIEWED.value,
        )
    )

    payload = map_product_to_response(product)

    assert payload.main_image == "https://cdn.mvn.by/products/variants/original/source.webp"
    assert payload.card_image == "https://cdn.mvn.by/products/variants/original/source.webp"
    assert payload.full_image == "https://cdn.mvn.by/products/variants/original/source.webp"
    assert payload.gallery_images[0].url == "https://cdn.mvn.by/products/variants/original/source.webp"
    assert payload.gallery_images[0].card_variant_url is None


def test_map_product_to_response_rewrites_legacy_images_to_public_original_variants():
    product = _product_with_variant()
    product.images = [
        "/media/products/source.webp",
        "media/products/extra.webp",
        "/media/products/missing.webp",
        "https://example.com/vendor.jpg",
    ]
    product.gallery_images[0].variants.append(
        ProductImageVariant(
            id=102,
            product_image_id=product.gallery_images[0].id,
            variant_type=ProductImageVariantType.ORIGINAL.value,
            url="https://cdn.mvn.by/products/variants/original/source.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
            manual_quality_status=ProductImageManualQualityStatus.UNREVIEWED.value,
        )
    )
    extra_image = ProductImage(
        id=11,
        product_id=product.id,
        url="/media/products/extra.webp",
        is_installation_photo=False,
    )
    extra_image.variants = [
        ProductImageVariant(
            id=103,
            product_image_id=extra_image.id,
            variant_type=ProductImageVariantType.ORIGINAL.value,
            url="https://cdn.mvn.by/products/variants/original/extra.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
            manual_quality_status=ProductImageManualQualityStatus.UNREVIEWED.value,
        )
    ]
    product.gallery_images.append(extra_image)

    payload = map_product_to_response(product)

    assert payload.images == [
        "https://cdn.mvn.by/products/variants/original/source.webp",
        "https://cdn.mvn.by/products/variants/original/extra.webp",
        "https://example.com/vendor.jpg",
    ]


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
        specs={"area_m2": 25},
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


def test_map_product_to_response_serializes_public_series():
    series = ProductSeries(
        id=7,
        title="Elite",
        slug="elite",
        description="Quiet inverter product line",
        hero_image="/media/series/elite.webp",
        is_published=True,
    )
    product = Product(
        id=1,
        title="Elite 25",
        slug="elite-25",
        description="",
        price=1200,
        specs={"area_m2": 25},
        is_published=True,
        series_id=series.id,
    )
    product.series = series

    payload = map_product_to_response(product)

    assert payload.series is not None
    assert payload.series.model_dump() == {
        "id": 7,
        "title": "Elite",
        "slug": "elite",
        "tagline": None,
        "short_description": None,
        "description": "Quiet inverter product line",
        "hero_image": "/media/series/elite.webp",
        "gallery_images": [],
        "features": [],
        "catalog_features": [],
        "brand_features": [],
        "feature_blocks": [],
        "content_blocks": [],
        "footnotes": [],
        "seo_title": None,
        "seo_description": None,
        "source_url": None,
    }


def test_map_product_to_response_hides_unpublished_series():
    series = ProductSeries(
        id=8,
        title="Draft",
        slug="draft",
        is_published=False,
    )
    product = Product(
        id=1,
        title="Draft 25",
        slug="draft-25",
        description="",
        price=1200,
        specs={"area_m2": 25},
        is_published=True,
        series_id=series.id,
    )
    product.series = series

    payload = map_product_to_response(product)

    assert payload.series is None


def test_map_product_to_response_projects_offer_prices_without_mutating_product():
    product = Product(
        id=1,
        title="Shared product",
        slug="shared-product",
        price=9000,
        old_price=9500,
        specs={"area_m2": 25},
        is_published=True,
    )
    sibling = Product(
        id=2,
        title="Shared sibling",
        slug="shared-sibling",
        price=10000,
        old_price=10500,
        specs={"area_m2": 35},
        is_published=True,
    )

    payload = map_product_to_response(
        product,
        series_siblings=[sibling],
        pricing=(3000, 3500),
        sibling_pricing={2: (4000, 4500)},
    )

    assert (payload.price, payload.old_price) == (3000, 3500)
    assert (
        payload.series_siblings[0].price,
        payload.series_siblings[0].old_price,
    ) == (4000, 4500)
    assert (product.price, product.old_price) == (9000, 9500)
    assert (sibling.price, sibling.old_price) == (10000, 10500)
