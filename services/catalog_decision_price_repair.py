"""Exact supplier-price review: 167 kinds and 319 field paths on 67 cards."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from urllib.parse import quote

from services.catalog_decision_data_repair import RepairBlocked, digest
from services.catalog_decision_source_repair import (
    IDENTITY_KEYS, PRODUCT_STATE_KEYS, SCOPE_IDS, _check_components, product_identity, product_projection,
)
from services.product_cooling_capacity import nominal_cooling_capacity

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog_source_repairs/catalog-decision-1190-price.json"
REVIEWED_MANIFEST_SHA256 = "3820ad0a32e02a3be52a16b391367307cead45cbd09c2a3491e8f16724d7402d"
SPEC_KEYS = frozenset({"capacity_cooling_kw", "model_indoor", "model_outdoor", "winter_kit",
                       "power_supply_voltage", "power_cons_cooling_kw", "power_cons_heating_kw"})
ALLOWED_PATHS = {"power_cooling"} | {f"specs.{key}" for key in SPEC_KEYS} | {f"specs.__typed_specs.{key}" for key in SPEC_KEYS}
HOLD_IDS = frozenset({188, 189, 191, 1004, 1005, 1080, 1082, 1084})


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    if digest(manifest) != REVIEWED_MANIFEST_SHA256 or manifest.get("schema_version") != 3 or manifest.get("issue") != 1190:
        raise RepairBlocked("Unreviewed price-first manifest; any scope or field change requires code review")
    rows = manifest["products"]
    if len(rows) != 217 or {r["identity"]["id"] for r in rows} != SCOPE_IDS:
        raise RepairBlocked("Manifest must contain all and only the original 217 IDs")
    sources = {(s["source_url"], s["source_sha256"]) for s in manifest["sources"]}
    changed, technical, paths = 0, 0, 0
    for row in rows:
        if set(row["identity"]) != IDENTITY_KEYS or row["before_sha256"] != digest(row["before"]) or row["target_sha256"] != digest(row["target"]):
            raise RepairBlocked("Missing exact identity, before or target guards")
        fields, patches = row["fields_set"], row["patches"]
        if fields:
            changed += 1
            if (fields != {"product_kind": "complete_split_system"} or row["before"]["product_kind"] != "other"
                    or row["identity"]["id"] in HOLD_IDS or row["disposition"] != "approved_system"
                    or row["proof"] != {"single_compatible_pair": True, "positive_system_price": True}):
                raise RepairBlocked("Only the individually approved priced single systems can change kind")
        elif patches or row["before"] != row["target"] or row["disposition"] == "approved_system":
            raise RepairBlocked("Held products must remain entirely unchanged")
        if patches:
            technical += 1
            paths += len(patches)
            if len({p["path"] for p in patches}) != len(patches) or any(p["path"] not in ALLOWED_PATHS or p["before"] == p["after"] for p in patches):
                raise RepairBlocked("Unreviewed, duplicate or unchanged technical field")
        evidence = [*row["evidence"], *(e for patch in patches for e in patch["evidence"])]
        if fields and (not row["evidence"] or any(not patch["evidence"] for patch in patches)):
            raise RepairBlocked("Each approved kind and field requires source evidence")
        if any((e["source_url"], e["source_sha256"]) not in sources or not e["locator"] for e in evidence):
            raise RepairBlocked("Missing exact source hash and locator")
    if (changed, technical, paths) != (167, 67, 319):
        raise RepairBlocked("The exact approved scope is 167 kinds and 319 field paths on 67 cards")


def apply_operation(product: Any, operation: dict) -> None:
    """Replace only reviewed keys; assigning a fresh JSON object tracks the edit."""
    for key, value in operation["fields_set"].items():
        if key != "product_kind":
            raise RepairBlocked("Unreviewed core field")
        setattr(product, key, value)
    specs = deepcopy(product.specs)
    for patch in operation["patches"]:
        path = patch["path"]
        if path not in ALLOWED_PATHS:
            raise RepairBlocked("Unreviewed technical path")
        if path == "power_cooling":
            product.power_cooling = patch["after"]
        else:
            parts, target = path.split(".")[1:], specs
            for key in parts[:-1]:
                target = target.setdefault(key, {})
            target[parts[-1]] = deepcopy(patch["after"])
    if operation["patches"]:
        product.specs = specs


def _verify_target(product: Any, row: dict, commerce: dict, *, already_applied: bool) -> None:
    # Do not copy ORM instrumentation or mark a live row dirty during a dry-run.
    target = SimpleNamespace(**{key: getattr(product, key) for key in
                               (*PRODUCT_STATE_KEYS, "id", "price", "old_price", "tags", "brand", "series")},
                             specs=deepcopy(product.specs))
    if not already_applied:
        for patch in row["patches"]:
            value, exists = {"specs": product.specs, "power_cooling": product.power_cooling}, True
            for key in patch["path"].split("."):
                if not isinstance(value, dict) or key not in value:
                    value, exists = None, False
                    break
                value = value[key]
            if exists != patch["before_exists"] or value != patch["before"]:
                raise RepairBlocked(f"Product {product.id}: exact technical before value changed")
        apply_operation(target, row)
    _check_components(target)
    if product_projection(target, commerce) != row["target"]:
        raise RepairBlocked(f"Product {product.id}: technical target differs from reviewed fields")
    if any(p["path"] == "power_cooling" for p in row["patches"]):
        expected = next(p["after"] for p in row["patches"] if p["path"] == "power_cooling")
        typed = target.specs.get("__typed_specs", {}).get("capacity_cooling_kw", {})
        if nominal_cooling_capacity(target.specs, fallback=target.power_cooling) != expected or any(typed.get(k) != expected for k in ("value", "nominal")):
            raise RepairBlocked(f"Product {product.id}: canonical, core and typed nominal disagree")


def build_plan(manifest: dict, products: Iterable[Any], commerce_by_id: dict[int, dict], *, now: datetime | None = None) -> dict:
    validate_manifest(manifest)
    products = list(products)
    by_id = {p.id: p for p in products}
    if len(products) != 217 or by_id.keys() != SCOPE_IDS or commerce_by_id.keys() != SCOPE_IDS:
        raise RepairBlocked("Expected the exact 217 scoped products and commerce states")
    observed, operations, held, statuses = [], [], [], set()
    for row in sorted(manifest["products"], key=lambda r: r["identity"]["id"]):
        product = by_id[row["identity"]["id"]]
        if product_identity(product) != row["identity"]:
            raise RepairBlocked(f"Product {product.id}: reviewed identity changed")
        actual = product_projection(product, commerce_by_id[product.id])
        if actual != row["before"] and actual != row["target"]:
            raise RepairBlocked(f"Product {product.id}: reviewed product or commercial state changed")
        observed.append({"identity": row["identity"], "state_sha256": digest(actual)})
        if not row["fields_set"]:
            held.append({"id": product.id, "disposition": row["disposition"]})
            continue
        applied = actual == row["target"]
        _verify_target(product, row, commerce_by_id[product.id], already_applied=applied)
        statuses.add("after" if applied else "before")
        if not applied:
            operations.append({"id": product.id, "identity": row["identity"], "before": actual,
                               "target": row["target"], "fields_set": row["fields_set"],
                               "patches": row["patches"], "evidence": row["evidence"]})
    if len(statuses) > 1:
        raise RepairBlocked("Partial repair across reviewed products; inspect before proceeding")
    ids = [op["id"] for op in operations]
    paths = {f"/brands/{quote(by_id[pid].brand.slug, safe='')}/series/{quote(by_id[pid].series.slug, safe='')}/"
             for pid in ids if by_id[pid].series and by_id[pid].brand}
    payload = {
        "ready": True, "issue": 1190, "manifest_sha256": digest(manifest), "sources": manifest["sources"],
        "scoped_product_ids": sorted(SCOPE_IDS), "observed": observed, "operations": operations,
        "changed": len(operations), "product_ids": ids, "blocked_items": held,
        "technical_changes": {"products": sum(bool(op["patches"]) for op in operations),
                              "fields": sum(len(op["patches"]) for op in operations)},
        "brand_slugs": sorted({by_id[pid].brand.slug for pid in ids if by_id[pid].brand}),
        "series_paths": sorted(paths), "manual_kind_provenance": "unavailable_in_product_schema",
        "manual_review_required": bool(operations),
    }
    payload["state_digest"] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload.update(created_at=now.isoformat(), expires_at=(now + timedelta(minutes=30)).isoformat())
    payload["plan_digest"] = digest(payload)
    return payload
