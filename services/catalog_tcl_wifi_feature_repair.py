"""Move mixed TCL series Wi-Fi claims to the variants that include a module."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


EXPECTED_PRODUCTS = {
    119: ("TCL Elite TAC-09CHSD/XA71IN", 10, "builtin"),
    120: ("TCL Elite TAC-12CHSD/XA71IN", 10, "builtin"),
    121: ("TCL Elite TAC-18CHSD/XA71IN", 10, "builtin"),
    122: ("TCL Elite TAC-24CHSD/XA71IN", 10, "builtin"),
    159: ("TCL Elite TAC-09CHSD/XA71IF", 10, "ready"),
    715: ("TCL Elite TAC-12CHSD/XA71IF", 10, "ready"),
    1236: ("Сплит-система TCL SaveIN AI Inverter TAC-09CHSD/ZG11IF", 189, "ready"),
    1237: ("Сплит-система TCL SaveIN AI Inverter TAC-12CHSD/ZG11IF", 189, "ready"),
    1238: ("Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-09CHSD/ZG11IHB", 189, "builtin"),
    1239: ("Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-12CHSD/ZG11IHB", 189, "builtin"),
    1240: ("Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-18CHSD/ZG11IHB", 189, "builtin"),
    1241: ("Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-24CHSD/ZG11IHB", 189, "builtin"),
}
EXPECTED_SERIES_LINKS = {(10, 27): 229, (189, 27): 257, (189, 40): 120}
BUILTIN_PRODUCT_LINKS = frozenset(
    {(product_id, 27) for product_id in (119, 120, 121, 122, 1238, 1239, 1240, 1241)}
    | {(product_id, 40) for product_id in (1238, 1239, 1240, 1241)}
)
EXISTING_DERIVED_LINKS = frozenset({(product_id, 40) for product_id in (119, 120, 121, 122)})


def tcl_wifi_feature_plan(
    products: Iterable[Any],
    series_links: Iterable[Any],
    product_links: Iterable[Any],
) -> tuple[dict[str, Any], list[Any], list[tuple[int, int, int]]]:
    product_map = {product.id: product for product in products}
    if product_map.keys() != EXPECTED_PRODUCTS.keys():
        raise ValueError(f"Expected exact TCL product set; missing: {sorted(EXPECTED_PRODUCTS.keys() - product_map.keys())}")
    for product_id, (title, series_id, state) in EXPECTED_PRODUCTS.items():
        product = product_map[product_id]
        specs = product.specs or {}
        if product.title != title or product.series_id != series_id:
            raise ValueError(f"Product {product_id} differs from reviewed model or series")
        if specs.get("wifi_state") != state or specs.get("wifi_ready") != (True if state == "builtin" else "ready"):
            raise ValueError(f"Product {product_id} Wi-Fi state differs from reviewed value")

    series_map = {(link.series_id, link.feature_id): link for link in series_links}
    if series_map.keys() != EXPECTED_SERIES_LINKS.keys():
        raise ValueError("Reviewed series Wi-Fi links changed")
    for key, link_id in EXPECTED_SERIES_LINKS.items():
        link = series_map[key]
        if link.id != link_id or link.source != "manual" or any(
            getattr(link, key, None) is not None
            for key in ("override_title", "override_description", "override_media_id", "override_image_url", "override_icon", "override_footnote")
        ):
            raise ValueError(f"Series link {key} differs from reviewed assignment")

    product_link_map = {(link.product_id, link.feature_id): link for link in product_links}
    if product_link_map.keys() - BUILTIN_PRODUCT_LINKS - EXISTING_DERIVED_LINKS:
        raise ValueError("Optional-module variants have an unexpected product Wi-Fi link")
    for key in EXISTING_DERIVED_LINKS:
        link = product_link_map.get(key)
        if link is None or link.source != "derived" or not link.is_enabled:
            raise ValueError(f"Existing derived Wi-Fi assignment {key} changed")
    additions: list[tuple[int, int, int]] = []
    for product_id, feature_id in sorted(BUILTIN_PRODUCT_LINKS):
        series_id = EXPECTED_PRODUCTS[product_id][1]
        sort_order = series_map[(series_id, feature_id)].sort_order
        link = product_link_map.get((product_id, feature_id))
        if link is None:
            additions.append((product_id, feature_id, sort_order))
        elif link.source != "manual" or not link.is_enabled or link.sort_order != sort_order:
            raise ValueError(f"Product feature link {(product_id, feature_id)} differs from reviewed assignment")
    disables = [link for link in series_map.values() if link.is_enabled]

    digest_input = {
        "products": [
            (product_id, hashlib.sha256(json.dumps(product_map[product_id].specs or {}, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest())
            for product_id in sorted(product_map)
        ],
        "series_links": [(key, link.id, link.source, link.is_enabled, link.sort_order) for key, link in sorted(series_map.items())],
        "product_links": [(key, link.id, link.source, link.is_enabled, link.sort_order) for key, link in sorted(product_link_map.items())],
        "additions": additions,
    }
    digest = hashlib.sha256(json.dumps(digest_input, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return ({
        "matched_products": len(product_map),
        "disable_series_links": sorted((link.series_id, link.feature_id) for link in disables),
        "add_product_links": [(product_id, feature_id) for product_id, feature_id, _ in additions],
        "changed": bool(disables or additions),
        "plan_digest": digest,
    }, disables, additions)
