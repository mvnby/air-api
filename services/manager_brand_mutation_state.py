from __future__ import annotations

from copy import deepcopy
from typing import Any

from models import Brand, Feature, ProductSeries


def snapshot_brand(brand: Brand) -> tuple[object, ...]:
    return (
        brand.title,
        brand.slug,
        brand.logo_url,
        brand.description,
        brand.is_published,
        brand.sort_order,
    )


def snapshot_brand_feature(feature: Feature) -> tuple[object, ...]:
    return (
        feature.name,
        feature.slug,
        feature.full_description,
        feature.image_url,
        feature.icon,
        feature.footnote,
        feature.source_url,
        tuple(feature.aliases or []),
        feature.is_active,
        feature.sort_order,
    )


def snapshot_brand_series(series: ProductSeries) -> tuple[object, ...]:
    return (
        series.brand_id,
        series.title,
        series.slug,
        series.tagline,
        series.short_description,
        series.description,
        series.hero_image,
        deepcopy(series.gallery_images or []),
        deepcopy(series.features or []),
        deepcopy(series.feature_blocks or []),
        deepcopy(series.content_blocks or []),
        deepcopy(series.footnotes or []),
        series.seo_title,
        series.seo_description,
        series.source_url,
        series.is_published,
        series.sort_order,
    )


def normalize_brand_feature_ids(value: Any) -> tuple[int, ...]:
    normalized: set[int] = set()
    for item in value or []:
        try:
            feature_id = int(item)
        except (TypeError, ValueError):
            continue
        if feature_id > 0:
            normalized.add(feature_id)
    return tuple(sorted(normalized))
