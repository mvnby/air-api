"""Shared serializers for public product series payloads."""

from typing import Any, List

from models import ProductSeries
from schemas import ProductSeriesBrandFeatureResponse, ProductSeriesResponse
from services.feature_scope_policy import FeatureScopePolicy
from services.public_catalog_disclosure import (
    CANONICAL_PUBLIC_DISCLOSURE,
    PublicCatalogDisclosurePolicy,
)


def serialize_series_brand_features(
    series: ProductSeries,
    *,
    disclosure_policy: PublicCatalogDisclosurePolicy = CANONICAL_PUBLIC_DISCLOSURE,
) -> List[ProductSeriesBrandFeatureResponse]:
    # Relationships must be eager-loaded by callers. Reading __dict__ avoids
    # accidental async lazy loads from synchronous serializers.
    links = list(getattr(series, "__dict__", {}).get("feature_links") or [])
    if not links:
        return []

    payload: list[ProductSeriesBrandFeatureResponse] = []
    for link in links:
        feature = getattr(link, "__dict__", {}).get("feature")
        if not feature or not getattr(feature, "is_active", False):
            continue
        if not FeatureScopePolicy.allows_target(
            feature,
            target_type="series",
            brand_id=series.brand_id,
        ):
            continue
        item = ProductSeriesBrandFeatureResponse(
            id=feature.id,
            title=getattr(link, "override_title", None) or feature.name,
            slug=feature.slug,
            text=(
                getattr(link, "override_description", None)
                if getattr(link, "override_description", None) is not None
                else feature.full_description
            ),
            image_url=getattr(link, "override_image_url", None) or feature.image_url,
            icon=getattr(link, "override_icon", None) or feature.icon,
            footnote=getattr(link, "override_footnote", None) or feature.footnote,
            source_url=feature.source_url,
            aliases=_normalize_string_list(feature.aliases),
            is_published=feature.is_active,
            sort_order=int(
                getattr(link, "sort_order", None)
                if getattr(link, "sort_order", None) is not None
                else feature.sort_order or 0
            ),
        )
        item._disclose_source_url = disclosure_policy.expose_source_provenance
        payload.append(item)
    return sorted(payload, key=lambda item: (item.sort_order, item.title.casefold(), item.id))


def build_product_series_response(
    series: ProductSeries | None,
    *,
    disclosure_policy: PublicCatalogDisclosurePolicy = CANONICAL_PUBLIC_DISCLOSURE,
) -> ProductSeriesResponse | None:
    if not series or not series.is_published:
        return None
    payload = ProductSeriesResponse(
        id=series.id,
        title=series.title,
        slug=series.slug,
        tagline=series.tagline,
        short_description=series.short_description,
        description=series.description,
        hero_image=series.hero_image,
        gallery_images=series.gallery_images or [],
        features=series.features or [],
        brand_features=serialize_series_brand_features(
            series,
            disclosure_policy=disclosure_policy,
        ),
        catalog_features=list(getattr(series, "__dict__", {}).get("_resolved_features") or []),
        feature_blocks=series.feature_blocks or [],
        content_blocks=series.content_blocks or [],
        footnotes=series.footnotes or [],
        seo_title=series.seo_title,
        seo_description=series.seo_description,
        source_url=series.source_url,
    )
    payload._disclose_source_url = disclosure_policy.expose_source_provenance
    return payload


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out
