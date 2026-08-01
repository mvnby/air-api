from models import Brand, Feature, ProductSeries
from services.manager_brand_mutation_state import (
    normalize_brand_feature_ids,
    snapshot_brand,
    snapshot_brand_feature,
    snapshot_brand_series,
)


def test_brand_feature_ids_are_normalized_as_an_order_insensitive_set():
    assert normalize_brand_feature_ids([3, "2", 1, 3, 0, -1, None]) == (1, 2, 3)
    assert normalize_brand_feature_ids([2, 3, 1]) == (1, 2, 3)


def test_brand_mutation_snapshots_cover_the_manager_editable_fields():
    brand = Brand(
        title="Snapshot Brand",
        slug="snapshot-brand",
        logo_url="/brand.webp",
        description="Description",
        is_published=True,
        sort_order=3,
    )
    feature = Feature(
        name="Quiet",
        slug="quiet",
        category_id=1,
        full_description="Quiet mode",
        image_url="/quiet.webp",
        icon="moon",
        footnote="Model dependent",
        source_url="https://example.com/quiet",
        aliases=["silent"],
        is_active=True,
        sort_order=4,
    )
    series = ProductSeries(
        brand_id=1,
        title="Snapshot Series",
        slug="snapshot-series",
        tagline="Tagline",
        short_description="Short",
        description="Long",
        hero_image="/hero.webp",
        gallery_images=["/gallery.webp"],
        features=["Wi-Fi"],
        feature_blocks=[{"title": "Comfort", "text": "Text"}],
        content_blocks=[{"kind": "text", "text": "Content"}],
        footnotes=["Footnote"],
        seo_title="SEO title",
        seo_description="SEO description",
        source_url="https://example.com/series",
        is_published=True,
        sort_order=5,
    )

    brand_before = snapshot_brand(brand)
    feature_before = snapshot_brand_feature(feature)
    series_before = snapshot_brand_series(series)

    brand.description = "Changed"
    feature.aliases = ["silent", "quiet"]
    series.feature_blocks[0]["text"] = "Changed"

    assert snapshot_brand(brand) != brand_before
    assert snapshot_brand_feature(feature) != feature_before
    assert snapshot_brand_series(series) != series_before
