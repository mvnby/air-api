"""Build a narrow repair of indoor-unit filter fields from the visible spec."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

from services.spec_registry import build_typed_specs, canonical_indoor_type_slug


def repaired_indoor_specs(specs: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    """Preserve public specs and every unrelated internal value."""
    visible = specs.get("indoor_type")
    slug = canonical_indoor_type_slug(visible)
    if slug is None:
        return None
    old_typed = specs.get("__typed_specs") or {}
    if not isinstance(old_typed, dict):
        raise ValueError("__typed_specs must be an object")
    old_indoor = old_typed.get("indoor_type") or {}
    if not isinstance(old_indoor, dict):
        raise ValueError("__typed_specs.indoor_type must be an object")
    if specs.get("__filter_indoor_type") == slug and old_indoor.get("value") == slug:
        return None

    updated = dict(specs)
    updated["__filter_indoor_type"] = slug
    if old_indoor.get("value") != slug:
        typed = dict(old_typed)
        typed["indoor_type"] = build_typed_specs({"indoor_type": visible})["indoor_type"]
        updated["__typed_specs"] = typed
    return updated, slug


def indoor_repair_plan(products: Iterable[Any]) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any]]]]:
    changes: list[tuple[Any, dict[str, Any]]] = []
    digest_rows: list[dict[str, Any]] = []
    by_form: Counter[str] = Counter()
    by_issue: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    processed = 0
    for product in products:
        processed += 1
        original = dict(product.specs or {})
        result = repaired_indoor_specs(original)
        if result is None:
            continue
        updated, slug = result
        old_typed = (original.get("__typed_specs") or {}).get("indoor_type") or {}
        old_filter = original.get("__filter_indoor_type")
        old_value = old_typed.get("value")
        issues = []
        if old_filter != slug:
            issues.append("filter")
        if old_value != slug:
            issues.append("typed")
        for issue in issues:
            by_issue[issue] += 1
        by_form[slug] += 1
        changes.append((product, updated))
        digest_rows.append({
            "id": product.id,
            "old_specs_sha256": hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
            "new_filter": slug,
            "new_typed": (updated.get("__typed_specs") or {}).get("indoor_type"),
        })
        if len(samples) < 20:
            samples.append({"id": product.id, "form": slug, "old_filter": old_filter, "old_typed": old_value, "issues": issues})
    plan_digest = hashlib.sha256(json.dumps(digest_rows, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return ({"processed": processed, "changed": len(changes), "by_form": dict(sorted(by_form.items())), "by_issue": dict(sorted(by_issue.items())), "samples": samples, "plan_digest": plan_digest}, changes)
