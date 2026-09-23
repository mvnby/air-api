"""Read-only planning for retiring legacy product Wi-Fi tags."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

from services.catalog_user_wifi_repair import WIFI_FIELDS, WIFI_TYPED_FIELDS
from services.spec_normalizer import normalize_specs


WIFI_TAG_STATES = {"wifi-builtin": "builtin", "wifi-ready": "ready"}


def _source_state(specs: dict[str, Any]) -> str | None:
    state = specs.get("wifi_state")
    if state in ("builtin", "ready", "none"):
        return state
    ready = specs.get("wifi_ready")
    if ready is True or str(ready).lower() in ("true", "1"):
        return "builtin"
    if ready == "ready":
        return "ready"
    if ready is False or str(ready).lower() in ("false", "0"):
        return "none"
    return None


def wifi_tag_retirement_plan(
    tags: Iterable[Any],
    links: Iterable[Any],
    products: Iterable[Any],
    confirmed_states: dict[int, str],
) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any]]]]:
    tags = list(tags)
    links = list(links)
    by_tag_id = {tag.id: tag.slug for tag in tags}
    if len(by_tag_id) != len(tags) or set(by_tag_id.values()) - WIFI_TAG_STATES.keys():
        raise ValueError("Unexpected Wi-Fi tag taxonomy")
    by_product = {product.id: product for product in products}
    links_by_product: dict[int, list[tuple[int, str]]] = {}
    for link in links:
        if link.tag_id not in by_tag_id:
            raise ValueError("Wi-Fi link references an unreviewed tag")
        links_by_product.setdefault(link.product_id, []).append((link.tag_id, by_tag_id[link.tag_id]))
    if set(by_product) != set(links_by_product):
        raise ValueError("Wi-Fi links and reviewed products differ")

    spec_changes: list[tuple[Any, dict[str, Any]]] = []
    conflicts: list[int] = []
    states: Counter[str] = Counter()
    digest_rows: list[dict[str, Any]] = []
    for product_id in sorted(by_product):
        product = by_product[product_id]
        original = dict(product.specs or {})
        source_state = _source_state(original)
        product_links = links_by_product[product_id]
        if len(product_links) != 1 or source_state is None:
            raise ValueError(f"Product {product_id} has ambiguous Wi-Fi source or tags")
        tag_state = WIFI_TAG_STATES[product_links[0][1]]
        if source_state != tag_state:
            if confirmed_states.get(product_id) != source_state:
                raise ValueError(f"Product {product_id} Wi-Fi tag conflicts with unconfirmed specs")
            conflicts.append(product_id)

        target = normalize_specs({"wifi_ready": source_state})
        typed = original.get("__typed_specs") or {}
        if not isinstance(typed, dict):
            raise ValueError(f"Product {product_id} typed specs are not an object")
        complete = (
            all(original.get(key) == target[key] for key in WIFI_FIELDS)
            and all(typed.get(key) == target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS)
        )
        if not complete:
            updated = dict(original)
            updated.update({key: target[key] for key in WIFI_FIELDS})
            updated["__typed_specs"] = {
                **typed,
                **{key: target["__typed_specs"][key] for key in WIFI_TYPED_FIELDS},
            }
            spec_changes.append((product, updated))
        states[source_state] += 1
        digest_rows.append({
            "id": product_id,
            "old_specs_sha256": hashlib.sha256(
                json.dumps(original, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest(),
            "link": product_links[0],
            "source_state": source_state,
        })

    digest_payload = {
        "tags": sorted((tag.id, tag.slug) for tag in tags),
        "products": digest_rows,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    affected_ids_digest = hashlib.sha256(json.dumps(sorted(by_product)).encode()).hexdigest()
    return ({
        "matched_products": len(by_product),
        "removed_links": len(links),
        "deleted_tags": len(tags),
        "spec_updates": len(spec_changes),
        "source_states": dict(sorted(states.items())),
        "confirmed_tag_conflict_ids": conflicts,
        "affected_ids_sha256": affected_ids_digest,
        "plan_digest": digest,
    }, spec_changes)
