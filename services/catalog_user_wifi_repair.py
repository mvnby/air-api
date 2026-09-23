"""Exact MDV Wi-Fi corrections confirmed by the catalog owner."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from services.mdv_price_overrides import CONFIRMED_MANIFEST_PATH
from services.spec_normalizer import normalize_specs


WIFI_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state", "__filter_wifi", "__filter_wifi_builtin")
WIFI_TYPED_FIELDS = ("wifi_ready", "wifi_builtin", "wifi_state")


def load_user_wifi_manifest(path: Path = CONFIRMED_MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = manifest["wifi"]
    ids = [entry["id"] for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate product ID in user-confirmed Wi-Fi manifest")
    if any(entry["new_state"] not in ("builtin", "ready") for entry in entries):
        raise ValueError("Unsupported user-confirmed Wi-Fi state")
    return manifest


def user_wifi_repair_plan(
    products: Iterable[Any], manifest: dict[str, Any]
) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any]]]]:
    """Return a digest-guarded plan and precise product spec changes."""
    by_id = {product.id: product for product in products}
    entries = manifest["wifi"]
    ids = {entry["id"] for entry in entries}
    if set(by_id) != ids:
        raise ValueError("Reviewed products are missing or have extra IDs")

    changes: list[tuple[Any, dict[str, Any]]] = []
    digest_rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    for entry in entries:
        product = by_id[entry["id"]]
        original = dict(product.specs or {})
        indoor = str(original.get("model_indoor") or "").upper()
        outdoor = str(original.get("model_outdoor") or "").upper()
        if (
            product.title != entry["title"]
            or product.product_kind != entry["product_kind"]
            or (indoor, outdoor) != (
                entry["model_indoor"].upper(), (entry["model_outdoor"] or "").upper()
            )
        ):
            raise ValueError(f"Product {product.id} identity changed since review")

        target = normalize_specs({"wifi_ready": entry["new_state"]})
        typed = original.get("__typed_specs") or {}
        if not isinstance(typed, dict):
            raise ValueError(f"Product {product.id} typed specs are not an object")
        complete = (
            all(original.get(key) == target[key] for key in WIFI_FIELDS)
            and all(typed.get(key) == target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS)
        )
        if complete:
            continue
        if (
            (original.get("wifi_state"), original.get("wifi_ready"))
            not in ((entry["old_state"], entry["old_ready"]),
                    (target["wifi_state"], target["wifi_ready"]))
            or any(original.get(key) for key in ("wifi_module", "wi_fi", "wifi"))
        ):
            raise ValueError(f"Product {product.id} Wi-Fi source changed since review")

        updated = dict(original)
        updated.update({key: target[key] for key in WIFI_FIELDS})
        updated["__typed_specs"] = {
            **typed,
            **{key: target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS},
        }
        changes.append((product, updated))
        states[entry["new_state"]] += 1
        digest_rows.append({
            "id": product.id,
            "old_specs_sha256": hashlib.sha256(
                json.dumps(original, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest(),
            "target_state": entry["new_state"],
        })
    digest = hashlib.sha256(
        json.dumps(digest_rows, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return ({
        "matched": len(ids),
        "changed": len(changes),
        "wifi_states": dict(sorted(states.items())),
        "product_ids": [product.id for product, _ in changes],
        "plan_digest": digest,
    }, changes)
