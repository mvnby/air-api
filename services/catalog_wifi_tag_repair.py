"""Exact-model plan for missing TCL Wi-Fi tags already supported by specs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


WIFI_TAG_CORRECTIONS = {
    88: ("TCL BreezeIN 2.0 TAC-18CHSD/UG11V3AH", "wifi-builtin"),
    89: ("TCL BreezeIN 2.0 TAC-09CHSD/UG11V3AH", "wifi-builtin"),
    90: ("TCL BreezeIN 2.0 TAC-12CHSD/UG11V3AH", "wifi-builtin"),
    91: ("TCL BreezeIN 2.0 TAC-24CHSD/UG11V3AH", "wifi-builtin"),
    159: ("TCL Elite TAC-09CHSD/XA71IF", "wifi-ready"),
    715: ("TCL Elite TAC-12CHSD/XA71IF", "wifi-ready"),
}
WIFI_TAG_SLUGS = frozenset({"wifi-builtin", "wifi-ready"})


def wifi_tag_repair_plan(
    products: Iterable[Any],
    tags_by_product: Mapping[int, Iterable[str]],
) -> tuple[dict[str, Any], list[tuple[Any, str]]]:
    additions: list[tuple[Any, str]] = []
    digest_rows: list[dict[str, Any]] = []
    matched: set[int] = set()
    for product in products:
        expected = WIFI_TAG_CORRECTIONS.get(product.id)
        if expected is None:
            continue
        title, tag_slug = expected
        if product.title != title:
            raise ValueError(f"Product {product.id} title differs from reviewed model")
        matched.add(product.id)
        specs = product.specs or {}
        if tag_slug == "wifi-builtin":
            valid_state = specs.get("wifi_ready") is True and specs.get("wifi_state") == "builtin"
            valid_filter = specs.get("__filter_wifi_builtin") is True
        else:
            valid_state = specs.get("wifi_ready") == "ready" and specs.get("wifi_state") == "ready"
            valid_filter = specs.get("__filter_wifi_builtin") is False
        if not valid_state or not valid_filter or specs.get("__filter_wifi") is not True:
            raise ValueError(f"Product {product.id} Wi-Fi specs differ from reviewed state")
        tag_slugs = sorted(set(tags_by_product.get(product.id, ())))
        wifi_slugs = WIFI_TAG_SLUGS.intersection(tag_slugs)
        if wifi_slugs == {tag_slug}:
            continue
        if wifi_slugs:
            raise ValueError(f"Product {product.id} has a conflicting Wi-Fi tag")
        additions.append((product, tag_slug))
        digest_rows.append({
            "id": product.id,
            "old_specs_sha256": hashlib.sha256(json.dumps(specs, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(),
            "old_tags": tag_slugs,
            "new_tag": tag_slug,
        })
    missing = WIFI_TAG_CORRECTIONS.keys() - matched
    if missing:
        raise ValueError(f"Expected all reviewed products; missing IDs: {sorted(missing)}")
    digest = hashlib.sha256(json.dumps(digest_rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return ({"matched": len(matched), "changed": len(additions), "additions": [{"id": product.id, "tag": slug} for product, slug in additions], "plan_digest": digest}, additions)
