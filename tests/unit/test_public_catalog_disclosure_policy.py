import json

from api_contracts.public_catalog import PublicProductSearchItemResponse
from main import app
from models import Feature, FeatureSeriesLink, Product, ProductAttachment, ProductSeries
from schemas import CatalogResponse, ProductResponse, ProductSeriesResponse
from schemas_brand_series import ProductSeriesBrandFeatureResponse
from services.product_response_mapper import map_product_to_response
from services.public_catalog_disclosure import (
    CANONICAL_PUBLIC_DISCLOSURE,
    TENANT_NEUTRAL_PUBLIC_DISCLOSURE,
)
from services.public_catalog_service import PublicCatalogService
from services.public_catalog_visibility_service import PublicProductProjection


_INTERNAL_POLICY_FIELDS = {
    "disclose_legacy_availability",
    "disclose_source_url",
    "disclose_source",
}


def _projection(*, tenant_neutral: bool) -> PublicProductProjection:
    feature = Feature(
        id=31,
        category_id=1,
        brand_id=1,
        scope_type="brand",
        name="Private feature source",
        slug="private-feature-source",
        source_url="https://supplier.example/feature.pdf",
        is_active=True,
    )
    link = FeatureSeriesLink(
        id=41,
        series_id=21,
        feature_id=31,
    )
    link.feature = feature
    series = ProductSeries(
        id=21,
        brand_id=1,
        title="Private source series",
        slug="private-source-series",
        source_url="https://supplier.example/series.pdf",
        is_published=True,
    )
    series.feature_links = [link]
    product = Product(
        id=11,
        title="Disclosure product",
        slug="disclosure-product",
        price=9000,
        old_price=9500,
        series_id=21,
        source_url="https://supplier.example/product",
        specs={"area_m2": 35},
        is_published=True,
    )
    product.series = series
    product.attachments = [
        ProductAttachment(
            id=51,
            product_id=11,
            kind="manual",
            title="Manual",
            url="https://manufacturer.example/manual.pdf",
            source="supplier portal",
        )
    ]
    return PublicProductProjection(
        product=product,
        price=4000,
        old_price=4500,
        disclosure_policy=(
            TENANT_NEUTRAL_PUBLIC_DISCLOSURE
            if tenant_neutral
            else CANONICAL_PUBLIC_DISCLOSURE
        ),
    )


def _metrics() -> dict:
    return {
        "vitebsk_qty": 7,
        "minsk_qty": 6,
        "availability_status": "available_2_3_days",
        "min_cost_byn": 1234.56,
        "margin_abs_preview": 2765.44,
    }


def test_tenant_projection_redacts_deep_provenance_and_inventory_before_dump():
    projection = _projection(tenant_neutral=True)
    response = map_product_to_response(
        projection,
        supply_metrics=_metrics(),
    )

    assert response.vitebsk_qty == 0
    assert response.minsk_qty == 0
    assert response.public_stock_state is None
    assert response.availability_status == "available_2_3_days"
    assert response.delivery_min_days == 2
    assert response.delivery_max_days == 3

    payload = CatalogResponse(
        items=[response],
        meta={"total": 1, "page": 1, "limit": 20, "pages": 1},
    ).model_dump()
    product = payload["items"][0]
    assert "vitebsk_qty" not in product
    assert "minsk_qty" not in product
    assert "public_stock_state" not in product
    assert "source_url" not in product["series"]
    assert "source_url" not in product["series"]["brand_features"][0]
    assert "source" not in product["manuals"][0]

    search = PublicCatalogService._to_public_search_item(
        projection,
        _metrics(),
    )
    search_payload = search.model_dump()
    assert "vitebsk_qty" not in search_payload
    assert "minsk_qty" not in search_payload
    assert "public_stock_state" not in search_payload


def test_canonical_projection_preserves_legacy_contract_exactly():
    response = map_product_to_response(
        _projection(tenant_neutral=False),
        supply_metrics=_metrics(),
    )
    payload = response.model_dump()

    assert payload["vitebsk_qty"] == 7
    assert payload["minsk_qty"] == 6
    assert payload["availability_status"] == "available_2_3_days"
    assert payload["public_stock_state"] == "supplier_stock"
    assert payload["delivery_min_days"] == 2
    assert payload["delivery_max_days"] == 3
    assert payload["series"]["source_url"] == "https://supplier.example/series.pdf"
    assert payload["series"]["brand_features"][0]["source_url"] == (
        "https://supplier.example/feature.pdf"
    )
    assert payload["manuals"][0]["source"] == "supplier portal"


def test_internal_disclosure_controls_are_absent_from_schema_and_openapi():
    schemas = (
        ProductResponse.model_json_schema(mode="serialization"),
        ProductSeriesResponse.model_json_schema(mode="serialization"),
        ProductSeriesBrandFeatureResponse.model_json_schema(mode="serialization"),
        PublicProductSearchItemResponse.model_json_schema(mode="serialization"),
    )
    schema_text = json.dumps(schemas)
    openapi_text = json.dumps(app.openapi())

    for field_name in _INTERNAL_POLICY_FIELDS:
        assert field_name not in schema_text
        assert field_name not in openapi_text
