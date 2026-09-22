"""Source-backed, exact-model correction of ten MDV Wi-Fi states."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

from services.spec_normalizer import normalize_specs


# Confirmed against the MDV series pages; see docs/catalog-indoor-filter-repair.md.
WIFI_CORRECTIONS = {
    41: ("MDV INFINI On/Off R32 MDSAG-07HRN8/MDOAG-07HN8", "ready"),
    44: ("MDV INFINI On/Off R32 MDSAG-18HRN8/MDOAG-18HN8", "ready"),
    51: ("MDV INTEGRA Pro Black MDSBI-18HRFN8/MDOAI-18HFN8", "builtin"),
    52: ("MDV INTEGRA Pro Black MDSBI-09HRFN8/MDOAI-09HFN8", "builtin"),
    53: ("MDV INTEGRA Pro Black MDSBI-12HRFN8/MDOAI-12HFN8", "builtin"),
    54: ("MDV INTEGRA Pro Black MDSBI-24HRFN8/MDOAI-24HFN8", "builtin"),
    55: ("MDV INTEGRA Pro MDSAI-18HRFN8/MDOAI-18HFN8", "builtin"),
    56: ("MDV INTEGRA Pro MDSAI-09HRFN8/MDOAI-09HFN8", "builtin"),
    57: ("MDV INTEGRA Pro MDSAI-12HRFN8/MDOAI-12HFN8", "builtin"),
    58: ("MDV INTEGRA Pro MDSAI-24HRFN8/MDOAI-24HFN8", "builtin"),
}
WIFI_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state", "__filter_wifi", "__filter_wifi_builtin")
TYPED_WIFI_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state")


def repaired_wifi_specs(specs: dict[str, Any], state: str) -> dict[str, Any] | None:
    expected = normalize_specs({"wifi_ready": state})
    typed = specs.get("__typed_specs") or {}
    if not isinstance(typed, dict):
        raise ValueError("__typed_specs must be an object")
    if all(specs.get(key) == expected[key] for key in WIFI_FIELDS) and all(
        typed.get(key) == expected["__typed_specs"][key] for key in TYPED_WIFI_FIELDS
    ):
        return None
    if specs.get("wifi_ready") is not False or any(specs.get(key) for key in ("wifi_module", "wi_fi", "wifi")):
        raise ValueError("Unexpected Wi-Fi source value; inspect the product before changing it")
    updated = dict(specs)
    updated.update({key: expected[key] for key in WIFI_FIELDS})
    new_typed = dict(typed)
    new_typed.update({key: expected["__typed_specs"][key] for key in TYPED_WIFI_FIELDS})
    updated["__typed_specs"] = new_typed
    return updated


def wifi_repair_plan(products: Iterable[Any]) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any]]]]:
    changes: list[tuple[Any, dict[str, Any]]] = []
    digest_rows: list[dict[str, Any]] = []
    by_state: Counter[str] = Counter()
    matched: set[int] = set()
    for product in products:
        expected = WIFI_CORRECTIONS.get(product.id)
        if expected is None:
            continue
        title, state = expected
        if product.title != title:
            raise ValueError(f"Product {product.id} title differs from reviewed model")
        matched.add(product.id)
        original = dict(product.specs or {})
        updated = repaired_wifi_specs(original, state)
        if updated is None:
            continue
        changes.append((product, updated))
        by_state[state] += 1
        digest_rows.append({
            "id": product.id,
            "old_specs_sha256": hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
            "new_state": state,
        })
    if matched != WIFI_CORRECTIONS.keys():
        raise ValueError(f"Expected all reviewed products; missing IDs: {sorted(WIFI_CORRECTIONS.keys() - matched)}")
    digest = hashlib.sha256(json.dumps(digest_rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ({"matched": len(matched), "changed": len(changes), "by_state": dict(by_state), "product_ids": [product.id for product, _ in changes], "plan_digest": digest}, changes)
