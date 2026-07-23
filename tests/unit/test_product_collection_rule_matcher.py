from types import SimpleNamespace

from models import Product
from services.product_collection_rule_matcher import ProductCollectionRuleMatcher


def _product(**overrides) -> Product:
    payload = {
        "title": "Split",
        "slug": "split",
        "product_kind": "complete_split_system",
        "price": 1800,
        "is_inverter": True,
        "specs": {
            "area_m2": 35,
            "__filter_noise_min": 19,
            "__filter_min_heat": -20,
            "wifi_state": "builtin",
            "color": "Black",
        },
        "brand_id": 10,
        "series_id": 20,
    }
    payload.update(overrides)
    return Product(**payload)


def test_rule_matcher_accepts_supported_typed_conditions():
    product = _product()
    assert ProductCollectionRuleMatcher.matches(
        product,
        rule_config={
            "product_kinds": ["complete_split_system"],
            "min_price": 1500,
            "max_price": 2000,
            "min_area_m2": 25,
            "max_area_m2": 40,
            "max_noise_min_db": 20,
            "max_heating_min_c": -15,
            "is_inverter": True,
            "wifi_states": ["builtin"],
            "brand_ids": [10],
            "series_ids": [20],
            "colors": ["black"],
            "public_stock_states": ["supplier_stock"],
        },
        supply_metrics={"availability_status": "available_2_3_days"},
    )


def test_rule_matcher_rejects_missing_canonical_values_and_wrong_stock():
    product = _product(specs={"area_m2": 35})
    assert not ProductCollectionRuleMatcher.matches(
        product,
        rule_config={"max_noise_min_db": 20},
        supply_metrics={"availability_status": "in_stock_now"},
    )
    assert not ProductCollectionRuleMatcher.matches(
        product,
        rule_config={"public_stock_states": ["supplier_stock"]},
        supply_metrics={"availability_status": "in_stock_now"},
    )


def test_rule_matcher_requires_every_selected_effective_feature():
    product = _product()
    product.__dict__["_resolved_features"] = [
        SimpleNamespace(id=10),
        SimpleNamespace(id=20),
    ]
    assert ProductCollectionRuleMatcher.matches(
        product,
        rule_config={"feature_ids": [10, 20]},
        supply_metrics={},
    )
    assert not ProductCollectionRuleMatcher.matches(
        product,
        rule_config={"feature_ids": [10, 30]},
        supply_metrics={},
    )
