"""Bounded, source-reviewed KingHome repair; planning is independent of the DB."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from services.spec_normalizer import normalize_specs
from services.spec_registry import build_typed_specs

PDF_SHA256 = "d5bc15c528624cfcc6ad3660abcb7d4ac7b1c3b4d54a0c4a250b1bf6b5c41054"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1CZRHge7aOyrvGfLpiIZiIGPOe_8p_J1EvhRGv1kqigU/edit?gid=1720464199"
PRODUCT_IDS = frozenset([94, 95, 96, 97, 98, 99, 172, 173, 174, 175, *range(760, 779), *range(1297, 1310)])
PATCH_IDS = PRODUCT_IDS - {172, 760, 765, 767, 777, 778}
SERIES_IDS = frozenset([87, 88, 89, 90, 91, 92, 231, 232, 233])
SERIES_PATCH_IDS = SERIES_IDS - {88, 89}
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog_source_repairs/kinghome-2026.json"
WIFI_RAW = {"wifi_ready", "wifi_state", "wifi_builtin"}
WIFI_FILTERS = {"__filter_wifi", "__filter_wifi_builtin"}
ALLOWED_SPECS = {
    "airflow_max", "noise_indoor", "noise_outdoor", "temp_range_heat", "temp_range_cool",
    "self_cleaning", "ionizer", "width_indoor", "height_indoor", "depth_indoor", "weight_indoor",
    "weight_outdoor", "pipe_max_length", "pipe_max_height", "power_cons_cooling_kw",
    "power_cons_heating_kw", *WIFI_RAW,
}


class RepairBlocked(ValueError):
    """The exact source-reviewed scope or state is no longer available."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("brand") != {"id": 4, "title": "KINGHOME", "slug": "kinghome"}:
        raise RepairBlocked("Unexpected manifest brand/schema")
    if manifest.get("sources", {}).get("catalog_sha256") != PDF_SHA256 or manifest.get("sources", {}).get("supplier_sheet_url") != SHEET_URL:
        raise RepairBlocked("Unexpected official source identity")
    products, series = manifest.get("products", []), manifest.get("series", [])
    if len(products) != 42 or {p["identity"]["id"] for p in products} != PRODUCT_IDS:
        raise RepairBlocked("Manifest must contain exactly the 42 reviewed products")
    if len(series) != 9 or {s["identity"]["id"] for s in series} != SERIES_IDS:
        raise RepairBlocked("Manifest must contain exactly the nine reviewed series")
    patched = set()
    for row in products:
        identity = row["identity"]
        if identity.get("brand_id") != 4 or identity.get("series_id") not in SERIES_IDS:
            raise RepairBlocked("Product escapes the KingHome series scope")
        keys = set(row["specs_set"]) | set(row["specs_delete"]) | set(row["rebuild_typed"])
        if (set(row["specs_set"]) & set(row["specs_delete"])) or not (set(row["specs_set"]) | set(row["specs_delete"])) <= set(row["rebuild_typed"]):
            raise RepairBlocked("Raw edits must have one matching typed-family rebuild")
        if not keys <= ALLOWED_SPECS or not set(row["specs_delete"]) <= {"ionizer"}:
            raise RepairBlocked("Unreviewed specification field")
        dimensions = keys & {"width_indoor", "height_indoor", "depth_indoor"}
        if identity["series_id"] >= 231 and dimensions:
            confirmed = {"width_indoor": "1400", "height_indoor": "300", "depth_indoor": "700"}
            if identity["id"] != 1309 or {key: row["specs_set"].get(key) for key in dimensions} != confirmed:
                raise RepairBlocked("Only the user-confirmed dimensions of product 1309 are reviewed")
        if set(row["fields_set"]) - {"description"}:
            raise RepairBlocked("Unreviewed product field")
        if row.get("source_before_sha256") != digest(row["before"]):
            raise RepairBlocked("Reviewed source-before projection hash is invalid")
        if not keys <= row["before"]["specs"].keys() or not keys <= row["before"]["typed"].keys():
            raise RepairBlocked("Every touched raw/typed field requires an exact before guard")
        if not set(row["fields_set"]) <= row["before"]["fields_sha256"].keys():
            raise RepairBlocked("Every changed description requires a source-before hash")
        if keys or row["fields_set"]:
            patched.add(identity["id"])
    if patched != PATCH_IDS:
        raise RepairBlocked("Manifest patch scope differs from the reviewed 36 products")
    if {s["identity"]["id"] for s in series if s["fields_set"]} != SERIES_PATCH_IDS:
        raise RepairBlocked("Manifest patch scope differs from the reviewed seven series")
    for row in series:
        if row["identity"].get("brand_id") != 4 or set(row["fields_set"]) - {"description", "short_description"}:
            raise RepairBlocked("Unreviewed series mutation")


def present(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    return {"present": key in mapping, **({"value": mapping[key]} if key in mapping else {})}


def product_projection(product: Any, row: dict[str, Any]) -> dict[str, Any]:
    specs = product.specs or {}
    if not isinstance(specs, dict):
        raise RepairBlocked(f"Product {product.id}: specs must be an object")
    typed = specs.get("__typed_specs", {})
    if not isinstance(typed, dict):
        raise RepairBlocked(f"Product {product.id}: specs/typed layer must be objects")
    return {
        "specs": {key: present(specs, key) for key in row["before"]["specs"]},
        "typed": {key: present(typed, key) for key in row["before"]["typed"]},
        "filters": {key: present(specs, key) for key in row["before"]["filters"]},
        "fields_sha256": {key: digest(getattr(product, key)) for key in row["before"]["fields_sha256"]},
    }


def repaired_specs(specs: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild only reviewed raw/typed/filter families, retaining other values."""
    updated = deepcopy(specs)
    updated.update(deepcopy(row["specs_set"]))
    for key in row["specs_delete"]:
        updated.pop(key, None)
    keys = set(row["rebuild_typed"])
    filters: dict[str, Any] = {}
    if keys & WIFI_RAW:
        wifi = normalize_specs({"wifi_ready": row["specs_set"]["wifi_state"]})
        updated.update({key: wifi[key] for key in WIFI_RAW})
        filters.update({key: wifi[key] for key in WIFI_FILTERS})
        keys.update(WIFI_RAW)
    typed = deepcopy(updated.get("__typed_specs", {}))
    for key in keys:
        typed.pop(key, None)
    typed.update(build_typed_specs({key: updated[key] for key in keys if key in updated}))
    if keys:
        updated["__typed_specs"] = typed
    for raw, internal in [("noise_indoor", "__filter_noise_min"), ("temp_range_heat", "__filter_min_heat")]:
        if raw in keys:
            updated.pop(internal, None)
            if "min" in typed.get(raw, {}):
                filters[internal] = typed[raw]["min"]
    for key in row["specs_delete"]:
        updated.pop(f"__filter_{key}", None)
    updated.update(filters)
    return updated


def desired_projection(row: dict[str, Any]) -> dict[str, Any]:
    before = row["before"]
    specs = {key: cell["value"] for section in ("specs", "filters") for key, cell in before[section].items() if cell["present"]}
    specs["__typed_specs"] = {key: cell["value"] for key, cell in before["typed"].items() if cell["present"]}
    specs = repaired_specs(specs, row)
    result = {
        "specs": {key: present(specs, key) for key in before["specs"]},
        "typed": {key: present(specs.get("__typed_specs", {}), key) for key in before["typed"]},
        "filters": {key: present(specs, key) for key in before["filters"]},
        "fields_sha256": dict(before["fields_sha256"]),
    }
    result["fields_sha256"].update({key: digest(value) for key, value in row["fields_set"].items()})
    return result


def _check_identity(obj: Any, expected: dict[str, Any]) -> None:
    if any(getattr(obj, key, None) != value for key, value in expected.items()):
        raise RepairBlocked(f"Identity changed for reviewed row {expected['id']}")


def _index(rows: Iterable[Any], expected: frozenset[int], kind: str) -> dict[int, Any]:
    items = list(rows)
    indexed = {row.id: row for row in items}
    if len(indexed) != len(items) or set(indexed) != expected:
        raise RepairBlocked(f"Expected all and only reviewed {kind}")
    return indexed


def build_plan(manifest: dict[str, Any], products: Iterable[Any], series: Iterable[Any], brand: Any, *, now: datetime | None = None) -> dict[str, Any]:
    validate_manifest(manifest)
    _check_identity(brand, manifest["brand"])
    by_product = _index(products, PRODUCT_IDS, "products")
    by_series = _index(series, SERIES_IDS, "series")
    observed, operations, statuses = [], [], set()
    for row in sorted(manifest["products"], key=lambda r: r["identity"]["id"]):
        product = by_product[row["identity"]["id"]]
        _check_identity(product, row["identity"])
        actual, target = product_projection(product, row), desired_projection(row)
        observed.append({"kind": "product", "identity": row["identity"], "state_sha256": digest(actual)})
        if actual != row["before"] and actual != target:
            raise RepairBlocked(f"Product {product.id}: unknown or partially changed reviewed fields")
        if row["before"] != target:
            statuses.add("before" if actual == row["before"] else "after")
            if actual != target:
                operations.append({"kind": "product", "id": product.id, "identity": row["identity"], "before": actual, "target": target, "fields_set": row["fields_set"], "before_sha256": digest(actual), "after_sha256": digest(target)})
    for row in sorted(manifest["series"], key=lambda r: r["identity"]["id"]):
        obj = by_series[row["identity"]["id"]]
        _check_identity(obj, row["identity"])
        actual = {key: digest(getattr(obj, key)) for key in row["before_sha256"]}
        target = {**row["before_sha256"], **{key: digest(value) for key, value in row["fields_set"].items()}}
        observed.append({"kind": "series", "identity": row["identity"], "state_sha256": digest(actual)})
        if actual != row["before_sha256"] and actual != target:
            raise RepairBlocked(f"Series {obj.id}: unknown or partially changed reviewed fields")
        if row["before_sha256"] != target:
            statuses.add("before" if actual == row["before_sha256"] else "after")
            if actual != target:
                operations.append({"kind": "series", "id": obj.id, "fields_set": row["fields_set"], "before_sha256": digest(actual), "after_sha256": digest(target)})
    if len(statuses) > 1:
        raise RepairBlocked("Partial repair across scoped rows; inspect before proceeding")
    now = now or datetime.now(timezone.utc)
    payload = {
        "ready": True, "manifest_sha256": digest(manifest), "sources": manifest["sources"], "observed": observed,
        "operations": operations, "changed": len(operations),
        "product_ids": sorted(PRODUCT_IDS), "brand_slugs": [brand.slug],
        "series_paths": [f"/brands/{quote(brand.slug, safe='')}/series/{quote(row['identity']['slug'], safe='')}/" for row in manifest["series"]],
    }
    payload["state_digest"] = digest(payload)
    payload["created_at"] = now.isoformat()
    payload["expires_at"] = (now + timedelta(minutes=30)).isoformat()
    payload["plan_digest"] = digest(payload)
    return payload


def validate_reviewed_plan(reviewed: dict[str, Any], live: dict[str, Any], supplied_digest: str, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not isinstance(reviewed, dict):
        raise RepairBlocked("Reviewed plan must be a JSON object")
    unsigned = {key: value for key, value in reviewed.items() if key != "plan_digest"}
    if reviewed.get("plan_digest") != supplied_digest or digest(unsigned) != supplied_digest:
        raise RepairBlocked("Reviewed plan digest is invalid")
    try:
        created = datetime.fromisoformat(reviewed["created_at"])
        expires = datetime.fromisoformat(reviewed["expires_at"])
        valid = created <= now < expires and expires - created == timedelta(minutes=30)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RepairBlocked("Reviewed plan is expired or has an invalid validity window")
    if reviewed.get("manifest_sha256") != live["manifest_sha256"] or reviewed.get("state_digest") != live["state_digest"]:
        raise RepairBlocked("Manifest or scoped catalog state changed since review")
