from types import SimpleNamespace

import pytest

from services.catalog_wifi_tag_repair import WIFI_TAG_CORRECTIONS, wifi_tag_repair_plan


def _products():
    return [
        SimpleNamespace(
            id=product_id,
            title=title,
            specs={
                "wifi_ready": True if slug == "wifi-builtin" else "ready",
                "wifi_state": "builtin" if slug == "wifi-builtin" else "ready",
                "__filter_wifi": True,
                "__filter_wifi_builtin": slug == "wifi-builtin",
            },
        )
        for product_id, (title, slug) in WIFI_TAG_CORRECTIONS.items()
    ]


def test_wifi_tag_plan_is_exact_and_idempotent():
    products = _products()
    plan, additions = wifi_tag_repair_plan(products, {})
    assert plan["matched"] == 6
    assert plan["changed"] == 6
    assert {slug for _, slug in additions} == {"wifi-builtin", "wifi-ready"}

    repaired_tags = {product.id: [slug] for product, slug in additions}
    repeated, _ = wifi_tag_repair_plan(products, repaired_tags)
    assert repeated["changed"] == 0


def test_wifi_tag_plan_rejects_conflicting_state_or_tag():
    products = _products()
    products[0].specs["wifi_ready"] = False
    with pytest.raises(ValueError, match="Wi-Fi specs differ"):
        wifi_tag_repair_plan(products, {})

    products = _products()
    with pytest.raises(ValueError, match="conflicting Wi-Fi tag"):
        wifi_tag_repair_plan(products, {88: ["wifi-ready"]})
