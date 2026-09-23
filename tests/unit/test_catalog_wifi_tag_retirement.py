from types import SimpleNamespace

import pytest

from services.catalog_wifi_tag_retirement import wifi_tag_retirement_plan
from services.spec_normalizer import normalize_specs


def _fixtures():
    tags = [SimpleNamespace(id=18, slug="wifi-builtin"), SimpleNamespace(id=19, slug="wifi-ready")]
    links = [
        SimpleNamespace(product_id=1, tag_id=18),
        SimpleNamespace(product_id=2, tag_id=19),
        SimpleNamespace(product_id=3, tag_id=19),
    ]
    products = [
        SimpleNamespace(id=1, specs={"wifi_ready": True, "area_m2": 25, "__typed_specs": {"area_m2": {"value": 25}}}),
        SimpleNamespace(id=2, specs=normalize_specs({"wifi_ready": "ready"})),
        SimpleNamespace(id=3, specs=normalize_specs({"wifi_ready": "builtin"})),
    ]
    return tags, links, products


def test_retirement_preserves_spec_values_and_rejects_unreviewed_conflict():
    tags, links, products = _fixtures()
    with pytest.raises(ValueError, match="unconfirmed specs"):
        wifi_tag_retirement_plan(tags, links, products, {})

    plan, changes = wifi_tag_retirement_plan(tags, links, products, {3: "builtin"})
    assert plan["matched_products"] == 3
    assert plan["removed_links"] == 3
    assert plan["deleted_tags"] == 2
    assert plan["spec_updates"] == 1
    assert plan["confirmed_tag_conflict_ids"] == [3]
    assert changes[0][0].id == 1
    assert changes[0][1]["wifi_state"] == "builtin"
    assert changes[0][1]["area_m2"] == 25


def test_retirement_rejects_ambiguous_tags_and_is_empty_after_cleanup():
    tags, links, products = _fixtures()
    links.append(SimpleNamespace(product_id=1, tag_id=19))
    with pytest.raises(ValueError, match="ambiguous Wi-Fi"):
        wifi_tag_retirement_plan(tags, links, products, {3: "builtin"})

    plan, changes = wifi_tag_retirement_plan([], [], [], {})
    assert plan["matched_products"] == 0
    assert plan["removed_links"] == 0
    assert plan["deleted_tags"] == 0
    assert changes == []
