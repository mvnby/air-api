"""Exact, source-reviewed corrections for catalog specs in the Biocond price audit."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from services.mdv_price_overrides import MANIFEST_PATH
from services.spec_normalizer import normalize_specs


FORM_FIELDS = ("indoor_type", "__filter_indoor_type")
WIFI_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state", "__filter_wifi", "__filter_wifi_builtin")
WIFI_TYPED_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state")


def load_price_repair_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    form_ids = [entry["id"] for entry in manifest["indoor_forms"]]
    wifi_ids = [entry["id"] for entry in manifest["wifi"]]
    if len(set(form_ids + wifi_ids)) != len(form_ids) + len(wifi_ids):
        raise ValueError("A product is listed more than once in the catalog repair manifest")
    if any(entry["new_state"] not in ("ready", "builtin") for entry in manifest["wifi"]):
        raise ValueError("Unsupported Wi-Fi state in the catalog repair manifest")
    return manifest


def _typed_specs(specs: dict[str, Any]) -> dict[str, Any]:
    typed = specs.get("__typed_specs") or {}
    if not isinstance(typed, dict):
        raise ValueError("__typed_specs must be an object")
    return typed


def _form_change(product: Any, entry: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    original = dict(product.specs or {})
    target = normalize_specs({"indoor_type": entry["new_form"]})
    new_title = entry.get("new_title", entry["title"])
    typed = _typed_specs(original)
    complete = (
        product.title == new_title
        and all(original.get(key) == target[key] for key in FORM_FIELDS)
        and typed.get("indoor_type") == target["__typed_specs"]["indoor_type"]
    )
    if complete:
        return None
    if product.title != entry["title"] or original.get("indoor_type") != entry["old_form"]:
        raise ValueError(f"Product {product.id} form source or title changed since review")
    updated = dict(original)
    updated.update({key: target[key] for key in FORM_FIELDS})
    updated["__typed_specs"] = {**typed, "indoor_type": target["__typed_specs"]["indoor_type"]}
    return updated, new_title


def _wifi_change(product: Any, entry: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    original = dict(product.specs or {})
    target = normalize_specs({"wifi_ready": entry["new_state"]})
    typed = _typed_specs(original)
    complete = (
        product.title == entry["title"]
        and all(original.get(key) == target[key] for key in WIFI_FIELDS)
        and all(typed.get(key) == target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS)
    )
    if complete:
        return None
    if (
        product.title != entry["title"]
        or original.get("wifi_state") != entry["old_state"]
        or original.get("wifi_ready") != entry["old_ready"]
        or any(original.get(key) for key in ("wifi_module", "wi_fi", "wifi"))
    ):
        raise ValueError(f"Product {product.id} Wi-Fi source or title changed since review")
    updated = dict(original)
    updated.update({key: target[key] for key in WIFI_FIELDS})
    updated["__typed_specs"] = {
        **typed,
        **{key: target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS},
    }
    return updated, product.title


def price_spec_repair_plan(
    products: Iterable[Any], manifest: dict[str, Any]
) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any], str]]]:
    by_id = {product.id: product for product in products}
    expected_ids = {entry["id"] for entry in (*manifest["indoor_forms"], *manifest["wifi"])}
    if set(by_id) != expected_ids:
        raise ValueError(f"Expected {len(expected_ids)} reviewed products; missing or extra IDs")

    changes: list[tuple[Any, dict[str, Any], str]] = []
    digest_rows: list[dict[str, Any]] = []
    forms: Counter[str] = Counter()
    wifi: Counter[str] = Counter()
    for kind, entries, repair in (
        ("indoor_form", manifest["indoor_forms"], _form_change),
        ("wifi", manifest["wifi"], _wifi_change),
    ):
        for entry in entries:
            product = by_id[entry["id"]]
            result = repair(product, entry)
            if result is None:
                continue
            updated, new_title = result
            changes.append((product, updated, new_title))
            (forms if kind == "indoor_form" else wifi)[entry["new_form"] if kind == "indoor_form" else entry["new_state"]] += 1
            digest_rows.append({
                "id": product.id,
                "kind": kind,
                "old_title": product.title,
                "old_specs_sha256": hashlib.sha256(
                    json.dumps(product.specs or {}, sort_keys=True, ensure_ascii=False, default=str).encode()
                ).hexdigest(),
                "new_title": new_title,
                "target": entry["new_form"] if kind == "indoor_form" else entry["new_state"],
            })
    digest = hashlib.sha256(json.dumps(sorted(digest_rows, key=lambda row: row["id"]), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ({
        "matched": len(expected_ids),
        "changed": len(changes),
        "indoor_forms": dict(sorted(forms.items())),
        "wifi_states": dict(sorted(wifi.items())),
        "product_ids": sorted(product.id for product, _, _ in changes),
        "plan_digest": digest,
    }, changes)
