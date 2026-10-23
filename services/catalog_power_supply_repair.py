"""Pure planner for the exact source-reviewed electrical supply repair."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from services.spec_registry import REGISTRY_KEY_MAP, build_typed_specs

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog_source_repairs/power-supply-2026-10.json"
# Canonical JSON digest of the checked-in source evidence and exact before guards.
REVIEWED_MANIFEST_SHA256 = "6d0a39aeddcf56d933199d71f22dbdd60c195f1b1e12ec25d09b24b392c772f2"
POWER_KEYS = frozenset({
    "power_supply", "power_supply_voltage", "power_supply_indoor",
    "power_supply_outdoor", "power_supply_location",
})
IDENTITY_KEYS = frozenset({"id", "title", "slug", "brand_id", "series_id", "product_kind", "source_url"})
POWER_ALIASES = {
    key.strip().casefold(): value for key, value in REGISTRY_KEY_MAP.items()
    if value in POWER_KEYS
}
POWER_ALIASES.update({key: key for key in POWER_KEYS})


class RepairBlocked(ValueError):
    """A reviewed identity, source manifest or electrical value has drifted."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def canonical_power_key(key: str) -> str | None:
    return POWER_ALIASES.get(str(key).strip().casefold())


def is_power_key(key: str) -> bool:
    normalized = str(key).strip().casefold()
    if normalized.startswith("__filter_"):
        normalized = normalized[len("__filter_"):]
    return canonical_power_key(normalized) is not None or normalized.startswith("power_supply")


def power_projection(specs: Any) -> dict[str, Any]:
    """Capture the entire family, including unexpected aliases and typed keys."""
    if specs is None:
        specs = {}
    if not isinstance(specs, dict) or not isinstance(specs.get("__typed_specs", {}), dict):
        raise RepairBlocked("Raw and typed specifications must be JSON objects")
    return deepcopy({
        "specs": {key: value for key, value in specs.items() if is_power_key(key)},
        "typed": {key: value for key, value in specs.get("__typed_specs", {}).items() if is_power_key(key)},
    })


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("repair_id") != "catalog-power-supply-2026-10":
        raise RepairBlocked("Unexpected power repair schema/identity")
    brands, products = manifest.get("brands"), manifest.get("products")
    if not isinstance(brands, list) or not brands or not isinstance(products, list) or not products:
        raise RepairBlocked("Reviewed brands and products are required")
    brand_ids = {row["id"] for row in brands}
    if len(brand_ids) != len(brands) or any(set(row) != {"id", "title", "slug"} for row in brands):
        raise RepairBlocked("Duplicate or incomplete reviewed brands")
    ids = set()
    for row in products:
        identity = row["identity"]
        if set(identity) != IDENTITY_KEYS or identity["id"] in ids or identity["brand_id"] not in brand_ids:
            raise RepairBlocked("Duplicate, incomplete or out-of-brand product identity")
        ids.add(identity["id"])
        assignments, deletions = row["specs_set"], row["specs_delete"]
        if not assignments or not set(assignments) <= POWER_KEYS or set(assignments) & set(deletions):
            raise RepairBlocked("Only canonical power assignments may be reviewed")
        if len(deletions) != len(set(deletions)) or any(canonical_power_key(key) is None for key in deletions):
            raise RepairBlocked("Only explicitly reviewed power keys may be deleted")
        if any(not isinstance(value, str) or not value.strip() for value in assignments.values()):
            raise RepairBlocked("Electrical assignments require nonempty source-supported text")
        before = row["before"]
        if set(before) != {"specs", "typed"} or any(not isinstance(before[section], dict) for section in before):
            raise RepairBlocked("Before state must contain the complete raw/typed power projection")
        if any(not is_power_key(key) for section in before.values() for key in section):
            raise RepairBlocked("Before state may contain only power-family keys")
        if digest(before) != row["before_sha256"]:
            raise RepairBlocked("Before projection digest is invalid")
        for key in deletions:
            if key not in before["specs"]:
                raise RepairBlocked("Deleted raw key is not present in reviewed before state")
            canonical = canonical_power_key(key)
            if key not in POWER_KEYS and canonical not in assignments:
                raise RepairBlocked("An alias deletion requires a canonical source-supported replacement")
        if not row.get("evidence"):
            raise RepairBlocked("Every product requires source evidence")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if digest(manifest) != REVIEWED_MANIFEST_SHA256:
        raise RepairBlocked("Manifest differs from the checked-in source-reviewed digest")
    return manifest


def repaired_specs(specs: dict[str, Any] | None, row: dict[str, Any]) -> dict[str, Any]:
    """Change reviewed power keys; leave every unrelated JSON value untouched."""
    power_projection(specs)
    updated = deepcopy(specs or {})
    updated.update(deepcopy(row["specs_set"]))
    touched = set(row["specs_set"])
    for key in row["specs_delete"]:
        updated.pop(key, None)
        touched.add(canonical_power_key(key))
    typed = deepcopy(updated.get("__typed_specs", {}))
    for key in list(typed):
        if canonical_power_key(key) in touched:
            typed.pop(key)
    typed.update(build_typed_specs({key: updated[key] for key in touched if key in updated}))
    updated["__typed_specs"] = typed
    return updated


def desired_projection(row: dict[str, Any]) -> dict[str, Any]:
    before = row["before"]
    return power_projection(repaired_specs({
        **deepcopy(before["specs"]), "__typed_specs": deepcopy(before["typed"]),
    }, row))


def _index(rows: Iterable[Any], expected: set[int], kind: str) -> dict[int, Any]:
    values = list(rows)
    indexed = {row.id: row for row in values}
    if len(indexed) != len(values) or set(indexed) != expected:
        raise RepairBlocked(f"Missing or unexpected reviewed {kind}")
    return indexed


def _check_identity(obj: Any, identity: dict[str, Any]) -> None:
    if any(getattr(obj, key, None) != value for key, value in identity.items()):
        raise RepairBlocked(f"Reviewed identity changed: {identity['id']}")


def build_plan(manifest: dict[str, Any], products: Iterable[Any], brands: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    validate_manifest(manifest)
    by_product = _index(products, {r["identity"]["id"] for r in manifest["products"]}, "products")
    by_brand = _index(brands, {r["id"] for r in manifest["brands"]}, "brands")
    for identity in manifest["brands"]:
        _check_identity(by_brand[identity["id"]], identity)
    observed, operations, statuses = [], [], set()
    for row in sorted(manifest["products"], key=lambda value: value["identity"]["id"]):
        product = by_product[row["identity"]["id"]]
        _check_identity(product, row["identity"])
        actual, target = power_projection(product.specs), desired_projection(row)
        observed.append({"identity": row["identity"], "state_sha256": digest(actual)})
        if actual != row["before"] and actual != target:
            raise RepairBlocked(f"Product {product.id}: unknown, missing or partially changed power fields")
        if row["before"] != target:
            statuses.add("before" if actual == row["before"] else "after")
            if actual != target:
                operations.append({
                    "id": product.id, "identity": row["identity"],
                    "before": actual, "target": target,
                    "specs_set": row["specs_set"], "specs_delete": row["specs_delete"],
                    "before_sha256": digest(actual), "after_sha256": digest(target),
                })
    if len(statuses) > 1:
        raise RepairBlocked("Partial repair across reviewed products")
    payload = {
        "ready": True, "manifest_sha256": digest(manifest),
        "sources": manifest.get("sources", []), "observed": observed,
        "operations": operations, "changed": len(operations),
        "product_ids": sorted(by_product),
        "brand_slugs": sorted(brand.slug for brand in by_brand.values()),
    }
    payload["state_digest"] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload["created_at"] = now.isoformat()
    payload["expires_at"] = (now + timedelta(minutes=30)).isoformat()
    payload["plan_digest"] = digest(payload)
    return payload


def validate_reviewed_plan(reviewed: dict[str, Any], live: dict[str, Any], supplied_digest: str, *, now: datetime | None = None) -> None:
    if not isinstance(reviewed, dict):
        raise RepairBlocked("Reviewed plan must be a JSON object")
    unsigned = {key: value for key, value in reviewed.items() if key != "plan_digest"}
    if reviewed.get("plan_digest") != supplied_digest or digest(unsigned) != supplied_digest:
        raise RepairBlocked("Reviewed plan digest is invalid")
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(reviewed["created_at"])
        expires = datetime.fromisoformat(reviewed["expires_at"])
        valid = created <= now < expires and expires - created == timedelta(minutes=30)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RepairBlocked("Reviewed plan is expired or has an invalid validity window")
    # Compare the entire time-independent payload, not a caller-provided state hash.
    stable = lambda plan: {key: value for key, value in plan.items() if key not in {"created_at", "expires_at", "plan_digest"}}
    if stable(reviewed) != stable(live):
        raise RepairBlocked("Manifest or scoped catalog state changed since review")
