import pytest

from api_contracts.catalog_management import CatalogManagementFilters
from services.catalog_access_service import CatalogAccessService, CatalogCommercialAccessDenied


def test_delegated_editor_receives_no_purchase_metrics_without_mutating_source():
    product = {
        "id": 4, "title": "Shared product", "price": 1800,
        "min_cost_byn": 900, "recommended_price_byn": 1900,
        "margin_abs_preview": 900, "margin_pct_preview": 50,
        "specs": {"cooling_kw": 3.5},
    }
    response = {"items": [product], "meta": {"total": 1}}
    result = CatalogAccessService.project_product(response, is_platform_owner=False)
    assert result == {"items": [{
        "id": 4, "title": "Shared product", "price": 1800,
        "specs": {"cooling_kw": 3.5},
    }], "meta": {"total": 1}}
    assert product["min_cost_byn"] == 900
    assert CatalogAccessService.project_product(response, is_platform_owner=True) is response


def test_editor_cannot_infer_supplier_relationships_via_query_or_selection_filters():
    filters = CatalogManagementFilters(supplier_id=3)
    with pytest.raises(CatalogCommercialAccessDenied):
        CatalogAccessService.validate_filters(filters, is_platform_owner=False)
    CatalogAccessService.validate_filters(filters, is_platform_owner=True)
    CatalogAccessService.validate_filters(CatalogManagementFilters(brand_ids=[2]), is_platform_owner=False)
