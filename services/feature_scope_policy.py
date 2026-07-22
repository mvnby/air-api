from __future__ import annotations

from models import Feature, Product


class FeatureScopePolicy:
    """Pure applicability rules shared by resolvers and assignment commands."""

    @staticmethod
    def allows_brand(feature: Feature, brand_id: int | None) -> bool:
        if feature.scope_type == "brand":
            return feature.brand_id is not None and feature.brand_id == brand_id
        if feature.scope_type == "derived" and feature.brand_id is not None:
            return feature.brand_id == brand_id
        return True

    @staticmethod
    def allows_product(
        feature: Feature,
        product: Product,
        *,
        has_series_link: bool,
        has_product_link: bool,
        mode: str = "resolve",
    ) -> bool:
        if not FeatureScopePolicy.allows_brand(feature, product.brand_id):
            return False
        if mode == "suggestion":
            return feature.scope_type in {"universal", "derived"}
        if feature.scope_type == "series":
            return has_series_link
        if feature.scope_type == "product":
            return has_product_link or mode == "manual"
        if feature.scope_type == "derived" and mode == "manual":
            return has_product_link
        return True

    @staticmethod
    def allows_target(feature: Feature, *, target_type: str, brand_id: int | None) -> bool:
        if not FeatureScopePolicy.allows_brand(feature, brand_id):
            return False
        if target_type == "brand":
            return feature.scope_type in {"universal", "brand", "derived"}
        if target_type == "series":
            return feature.scope_type in {"universal", "brand", "series", "derived"}
        return False
