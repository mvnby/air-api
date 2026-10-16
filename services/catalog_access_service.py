"""Output and query boundaries for delegated shared-catalog editors."""


class CatalogCommercialAccessDenied(PermissionError):
    pass


class CatalogAccessService:
    COMMERCIAL_FIELDS = frozenset({
        "min_cost_byn", "recommended_price_byn", "margin_abs_preview", "margin_pct_preview",
    })

    @classmethod
    def project_product(cls, value, *, is_platform_owner: bool):
        if value is None or is_platform_owner:
            return value
        if isinstance(value, list):
            return [cls.project_product(item, is_platform_owner=False) for item in value]
        if "items" in value:
            return {**value, "items": [cls.project_product(item, is_platform_owner=False) for item in value["items"]]}
        return {key: item for key, item in value.items() if key not in cls.COMMERCIAL_FIELDS}

    @staticmethod
    def validate_filters(filters, *, is_platform_owner: bool):
        if not is_platform_owner and filters.supplier_id is not None:
            raise CatalogCommercialAccessDenied("Supplier filters require platform access")
