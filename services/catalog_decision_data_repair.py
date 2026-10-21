"""Exact reviewed repair of legacy decision-catalog kind and cooling fields."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

KIND_IDS = frozenset([94, 95, 96, 97, 98, 99, *range(1297, 1310)])
POWER_TARGETS = {
    179: 14.0, 180: 16.12, 181: 10.5, 182: 7.0, 183: 5.2,
    184: 5.3, 185: 5.2, 186: 7.0, 187: 10.55, 188: 14.0,
    189: 16.12, 190: 7.0, 192: 7.1, 193: 5.27, 196: 5.27,
}
BLOCKED_IDS = frozenset({191})
PRODUCT_IDS = KIND_IDS | POWER_TARGETS.keys() | BLOCKED_IDS
KINGHOME_PDF = "https://cdn.mvn.by/catalog-documents/original/d5bc15c528624cfcc6ad3660abcb7d4ac7b1c3b4d54a0c4a250b1bf6b5c41054.pdf"
TCL_PDF = "https://tcl-shop.by/doc/poluprom.pdf"
SUPPLIER_SHEET = "https://docs.google.com/spreadsheets/d/1oQIe3HonJQbTek7NTINg0x1eslNrJ6m_YaiOxRTD7-8/edit"
SOURCE_HASHES = {
    KINGHOME_PDF: "d5bc15c528624cfcc6ad3660abcb7d4ac7b1c3b4d54a0c4a250b1bf6b5c41054",
    TCL_PDF: "282cd48a2bf0f34fa531a7dc9619c8c9ebe7a3555ba02dedeff6d12dd6ad5f32",
    SUPPLIER_SHEET: "ae650424aef27bcd4d15c3e041deeee416ef1a492f7c6fbb019368facfdad1e9",
}
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog_source_repairs/catalog-decision-2026-10.json"
IDENTITY_KEYS = {"id", "title", "slug", "brand_id", "source_url", "series_id"}
BEFORE_KEYS = {"product_kind", "power_cooling", "specs_sha256", "tag_slugs"}


class RepairBlocked(ValueError):
    """An exact source, identity, catalog state or execution gate is missing."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _number(value: Any) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(str(value).strip().replace(",", "."))
        if not math.isfinite(number) or number <= 0:
            raise ValueError
        return number
    except (ValueError, TypeError):
        raise RepairBlocked("Cooling capacity must be one finite positive nominal value") from None


def _true(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "да", "есть", "в комплекте"}


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("sources") != SOURCE_HASHES:
        raise RepairBlocked("Unexpected manifest schema or reviewed sources")
    rows = manifest.get("products", [])
    if len(rows) != len(PRODUCT_IDS) or {row["identity"]["id"] for row in rows} != PRODUCT_IDS:
        raise RepairBlocked("Manifest must contain exactly the 35 reviewed products")
    for row in rows:
        identity, before, fields = row["identity"], row["before"], row["fields_set"]
        pid = identity["id"]
        if set(identity) != IDENTITY_KEYS or identity["brand_id"] != (4 if pid in KIND_IDS else 3):
            raise RepairBlocked("Unreviewed product identity or brand")
        if set(before) != BEFORE_KEYS or not _sha256(before["specs_sha256"]) or row.get("before_sha256") != digest(before):
            raise RepairBlocked("Missing exact before/specification guards")
        if before["tag_slugs"] != sorted(set(before["tag_slugs"])):
            raise RepairBlocked("Tag guard must be a canonical unique list")
        if pid in KIND_IDS:
            if fields != {"product_kind": "complete_split_system"} or before["product_kind"] not in {"other", "unknown"}:
                raise RepairBlocked("Kind repair escapes the exact legacy candidate scope")
        elif pid in POWER_TARGETS:
            if fields != {"power_cooling": POWER_TARGETS[pid]} or isinstance(fields.get("power_cooling"), bool):
                raise RepairBlocked("Unreviewed cooling-capacity target")
        elif fields or row.get("blocked_reason") != "blocked_source_conflict":
            raise RepairBlocked("Product 191 must remain unchanged pending source review")
        evidence = row.get("evidence", [])
        if not evidence or any(e.get("source_url") not in SOURCE_HASHES or e.get("source_sha256") != SOURCE_HASHES[e["source_url"]] or not e.get("locator") for e in evidence):
            raise RepairBlocked("Every row requires exact reviewed source hashes and locators")
        if pid in KIND_IDS and not any(e["source_url"] == KINGHOME_PDF for e in evidence):
            raise RepairBlocked("Kind evidence requires the exact KingHome catalog")
        if pid in POWER_TARGETS and not any(e["source_url"] in {TCL_PDF, SUPPLIER_SHEET} and e.get("capacity_cooling_kw") == POWER_TARGETS[pid] for e in evidence):
            raise RepairBlocked("Cooling target requires matching model/source capacity evidence")
        if pid == 191 and not {TCL_PDF, SUPPLIER_SHEET} <= {e["source_url"] for e in evidence}:
            raise RepairBlocked("Blocked product requires both conflicting sources")


def product_projection(product: Any) -> dict[str, Any]:
    if not isinstance(product.specs, dict):
        raise RepairBlocked(f"Product {product.id}: specifications must be an object")
    return {
        "product_kind": product.product_kind,
        "power_cooling": product.power_cooling,
        "specs_sha256": digest(product.specs),
        "tag_slugs": sorted({tag.slug for tag in product.tags}),
    }


def _check_source_facts(product: Any) -> None:
    specs = product.specs
    if product.id in KIND_IDS:
        system_type = str(specs.get("type") or "").strip().casefold()
        if not (_true(specs.get("includes_indoor_unit")) and _true(specs.get("includes_outdoor_unit")) and str(specs.get("indoor_units_count")) == "1"):
            raise RepairBlocked(f"Product {product.id}: explicit single-system component evidence is missing")
        if system_type not in {"сплит-система", "полупромышленный кондиционер"} or "cat-multi" in {tag.slug for tag in product.tags}:
            raise RepairBlocked(f"Product {product.id}: contradictory type or multi-split category")
    elif product.id in POWER_TARGETS:
        target = POWER_TARGETS[product.id]
        if _number(specs.get("capacity_cooling_kw")) != target:
            raise RepairBlocked(f"Product {product.id}: canonical nominal differs from reviewed source capacity")
        typed = specs.get("__typed_specs", {})
        if not isinstance(typed, dict):
            raise RepairBlocked(f"Product {product.id}: invalid typed specification layer")
        capacity = typed.get("capacity_cooling_kw")
        if capacity is not None:
            if not isinstance(capacity, dict) or not ({"nominal", "value"} & capacity.keys()):
                raise RepairBlocked(f"Product {product.id}: typed nominal is missing")
            if any(_number(capacity[key]) != target for key in ("nominal", "value") if key in capacity):
                raise RepairBlocked(f"Product {product.id}: typed nominal differs from reviewed source capacity")


def build_plan(manifest: dict[str, Any], products: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    validate_manifest(manifest)
    products = list(products)
    by_id = {product.id: product for product in products}
    if len(products) != len(by_id) or by_id.keys() != PRODUCT_IDS:
        raise RepairBlocked("Expected all and only the 35 reviewed products")
    observed, operations, blocked, statuses = [], [], [], set()
    for row in sorted(manifest["products"], key=lambda r: r["identity"]["id"]):
        product = by_id[row["identity"]["id"]]
        if any(getattr(product, key, None) != value for key, value in row["identity"].items()):
            raise RepairBlocked(f"Product {product.id}: reviewed identity changed")
        _check_source_facts(product)
        actual, target = product_projection(product), {**row["before"], **row["fields_set"]}
        if actual != row["before"] and actual != target:
            raise RepairBlocked(f"Product {product.id}: unknown or partially changed reviewed state")
        observed.append({"identity": row["identity"], "state_sha256": digest(actual)})
        if product.id in BLOCKED_IDS:
            blocked.append({"id": product.id, "reason": row["blocked_reason"], "evidence": row["evidence"]})
        elif row["before"] != target:
            statuses.add("before" if actual == row["before"] else "after")
            if actual != target:
                operations.append({"id": product.id, "identity": row["identity"], "before": actual, "target": target, "fields_set": row["fields_set"], "evidence": row["evidence"]})
    if len(statuses) > 1:
        raise RepairBlocked("Partial repair across reviewed products; inspect before proceeding")
    changed_ids = [op["id"] for op in operations]
    paths = set()
    for pid in changed_ids:
        product = by_id[pid]
        if product.series:
            paths.add(f"/brands/{quote(product.brand.slug, safe='')}/series/{quote(product.series.slug, safe='')}/")
    payload = {
        "ready": True, "manifest_sha256": digest(manifest), "sources": manifest["sources"],
        "observed": observed, "operations": operations, "changed": len(operations),
        "scoped_product_ids": sorted(PRODUCT_IDS), "product_ids": changed_ids,
        "brand_slugs": sorted({by_id[pid].brand.slug for pid in changed_ids}), "series_paths": sorted(paths),
        "blocked_items": blocked,
        "manual_kind_provenance": "unavailable_in_product_schema",
        "manual_review_required": any(op["id"] in KIND_IDS for op in operations),
    }
    payload["state_digest"] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload["created_at"] = now.isoformat()
    payload["expires_at"] = (now + timedelta(minutes=30)).isoformat()
    payload["plan_digest"] = digest(payload)
    return payload


def validate_reviewed_plan(reviewed: dict[str, Any], live: dict[str, Any], supplied_digest: str, *, manual_kind_review_digest: str | None = None, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not isinstance(reviewed, dict) or reviewed.get("plan_digest") != supplied_digest or digest({key: value for key, value in reviewed.items() if key != "plan_digest"}) != supplied_digest:
        raise RepairBlocked("Reviewed plan digest is invalid")
    reviewed_state = {key: value for key, value in reviewed.items() if key not in {"state_digest", "created_at", "expires_at", "plan_digest"}}
    if digest(reviewed_state) != reviewed.get("state_digest"):
        raise RepairBlocked("Reviewed plan state digest is invalid")
    try:
        created, expires = (datetime.fromisoformat(reviewed[key]) for key in ("created_at", "expires_at"))
        valid = created <= now < expires and expires - created == timedelta(minutes=30)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RepairBlocked("Reviewed plan is expired or has an invalid validity window")
    if reviewed.get("manifest_sha256") != live["manifest_sha256"] or reviewed.get("state_digest") != live["state_digest"]:
        raise RepairBlocked("Manifest or scoped catalog state changed since review")
    if live["manual_review_required"] and manual_kind_review_digest != supplied_digest:
        raise RepairBlocked("Manual kind provenance is unavailable; explicit manual review of this exact plan is required")
