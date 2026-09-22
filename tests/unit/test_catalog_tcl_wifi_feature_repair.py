from types import SimpleNamespace

import pytest

from services.catalog_tcl_wifi_feature_repair import (
    BUILTIN_PRODUCT_LINKS,
    EXISTING_DERIVED_LINKS,
    EXPECTED_PRODUCTS,
    EXPECTED_SERIES_LINKS,
    tcl_wifi_feature_plan,
)


def _fixture():
    products = [
        SimpleNamespace(
            id=product_id,
            title=title,
            series_id=series_id,
            specs={"wifi_state": state, "wifi_ready": True if state == "builtin" else "ready"},
        )
        for product_id, (title, series_id, state) in EXPECTED_PRODUCTS.items()
    ]
    series_links = [
        SimpleNamespace(
            id=link_id, series_id=series_id, feature_id=feature_id,
            source="manual", is_enabled=True, sort_order=50,
        )
        for (series_id, feature_id), link_id in EXPECTED_SERIES_LINKS.items()
    ]
    derived_links = [
        SimpleNamespace(id=index, product_id=pid, feature_id=fid, source="derived", is_enabled=True, sort_order=0)
        for index, (pid, fid) in enumerate(sorted(EXISTING_DERIVED_LINKS), 1)
    ]
    return products, series_links, derived_links


def test_repair_moves_mixed_series_links_only_to_builtin_products():
    products, series_links, derived_links = _fixture()
    plan, disables, additions = tcl_wifi_feature_plan(products, series_links, derived_links)

    assert plan["matched_products"] == 12
    assert len(disables) == 3
    assert {(pid, fid) for pid, fid, _ in additions} == BUILTIN_PRODUCT_LINKS
    assert all(EXPECTED_PRODUCTS[pid][2] == "builtin" for pid, _, _ in additions)

    for link in disables:
        link.is_enabled = False
    product_links = [
        SimpleNamespace(id=index, product_id=pid, feature_id=fid, source="manual", is_enabled=True, sort_order=order)
        for index, (pid, fid, order) in enumerate(additions, 1)
    ]
    repeated, _, _ = tcl_wifi_feature_plan(products, series_links, [*derived_links, *product_links])
    assert repeated["changed"] is False


def test_repair_rejects_changed_product_wifi_state():
    products, series_links, derived_links = _fixture()
    products[0].specs["wifi_state"] = "ready"
    with pytest.raises(ValueError, match="Wi-Fi state differs"):
        tcl_wifi_feature_plan(products, series_links, derived_links)
