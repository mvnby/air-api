"""Bounded, source-reviewed kind repair for the original 217 issue-1190 rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from services.catalog_decision_data_repair import RepairBlocked, digest
from services.product_kind_service import SPEC_BOOLEAN_FALSE_VALUES

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog_source_repairs/catalog-decision-1190.json"
REVIEWED_MANIFEST_SHA256 = "1ae8feb3c36db550ed7f15f8303188624dd9aaa8f5eeb2095b4b0be94b67c0ee"
SCOPE_IDS = frozenset({
    161, 162, 163, 164, 170, 179, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195,
    504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520, 521, 522, 523, 524,
    525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545,
    546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559, 560, 659, 660, 661, 662, 663, 664,
    665, 666, 667, 668, 669, 670, 671, 672, 673, 674, 675, 676, 677, 678, 923, 924, 925, 926, 927, 928, 930,
    931, 932, 933, 934, 935, 936, 937, 938, 939, 940, 941, 942, 943, 944, 945, 946, 947, 948, 949, 950, 951,
    952, 953, 954, 955, 956, 957, 958, 959, 960, 961, 962, 963, 964, 965, 966, 967, 968, 969, 970, 971, 972,
    973, 974, 975, 976, 977, 978, 979, 980, 981, 982, 983, 984, 985, 986, 987, 988, 989, 990, 991, 992, 993,
    994, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1080, 1081,
    1082, 1083, 1084, 1085, 1196, 1198, 1200, 1201, 1203, 1204, 1206, 1207, 1209, 1210, 1212, 1213, 1214,
    1215, 1216, 1217, 1218, 1219, 1220, 1221, 1222, 1223, 1224, 1225, 1226, 1227, 1229
})
IDENTITY_KEYS = {"id", "title", "slug", "brand_id", "series_id", "source_url_sha256"}
SUPPLIER_KEYS = ("id", "name", "code", "is_active", "spreadsheet_id", "spreadsheet_url")
PRODUCT_STATE_KEYS = ("product_kind", "power_cooling", "is_inverter", "is_published", "catalog_category_override", "series_assignment_source")
# Polling a feed must not invalidate an otherwise identical reviewed plan.
# Every business value, relation, source configuration and mapping date is guarded.
OFFER_OBSERVATIONS = {"last_seen_at", "updated_at"}
SOURCE_OBSERVATIONS = {"last_sync_at", "last_sync_status", "last_sync_error", "updated_at"}


def json_state(value: Any) -> Any:
    """Use the same Decimal/datetime representation in snapshots and ORM reads."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str, allow_nan=False))


def commerce_projection(record: dict, price_sources: Iterable[dict]) -> dict:
    mappings, supplier_ids = [], set()
    for mapping in sorted(record["supplier_mappings"], key=lambda row: row["id"]):
        supplier_ids.add(mapping["supplier_id"])
        supplier, offer = mapping["supplier"], mapping["offer"]
        mappings.append({
            "mapping": {key: value for key, value in mapping.items() if key not in {"supplier", "offer"}},
            "supplier": {key: supplier[key] for key in SUPPLIER_KEYS},
            "offer": {key: value for key, value in offer.items() if key not in OFFER_OBSERVATIONS} if offer else None,
        })
    return json_state({
        "mappings": mappings,
        "sources": [{key: value for key, value in source.items() if key not in SOURCE_OBSERVATIONS}
                    for source in sorted(price_sources, key=lambda row: row["id"]) if source["supplier_id"] in supplier_ids],
        "local_stocks": [{key: value for key, value in row.items() if key != "updated_at"}
                         for row in sorted(record["local_stocks"], key=lambda row: row["id"])],
    })


def product_projection(product: Any, commerce: dict) -> dict:
    return {
        **{key: getattr(product, key) for key in PRODUCT_STATE_KEYS},
        "specs_sha256": digest(product.specs), "tag_slugs": sorted({tag.slug for tag in product.tags}),
        "brand_slug": product.brand.slug if product.brand else None,
        "series_slug": product.series.slug if product.series else None,
        "retail_sha256": digest({"price": product.price, "old_price": product.old_price}),
        "commerce_sha256": digest(commerce),
    }


def product_identity(product: Any) -> dict:
    return {**{key: getattr(product, key) for key in IDENTITY_KEYS if key != "source_url_sha256"},
            "source_url_sha256": digest(product.source_url)}


def validate_manifest(manifest: dict) -> None:
    if digest(manifest) != REVIEWED_MANIFEST_SHA256 or manifest.get("schema_version") != 2 or manifest.get("issue") != 1190:
        raise RepairBlocked("Unreviewed issue-1190 manifest; the exact new manifest requires code review")
    rows = manifest["products"]
    if len(rows) != 217 or {row["identity"]["id"] for row in rows} != SCOPE_IDS:
        raise RepairBlocked("Manifest must contain all and only the original 217 IDs")
    sources = {(source["source_url"], source["source_sha256"]) for source in manifest["sources"]}
    for row in rows:
        if set(row["identity"]) != IDENTITY_KEYS or row["before_sha256"] != digest(row["before"]):
            raise RepairBlocked("Missing exact identity or before-state guard")
        fields, proof = row["fields_set"], row["proof"]
        if fields and (fields != {"product_kind": "complete_split_system"} or row["before"]["product_kind"] != "other"):
            raise RepairBlocked("Only the individually reviewed other-to-complete kind changes are allowed")
        if fields and (proof != {"indoor_count": 1, "outdoor_count": 1, "compatible_pair": True, "positive_system_price": True} or row["blocked_reasons"]):
            raise RepairBlocked("A kind candidate requires a confirmed priced single system without identity conflicts")
        if fields and row["nominal_review"]["conflicts"]:
            raise RepairBlocked("A nominal source conflict must remain unchanged pending review")
        if not fields and not row["blocked_reasons"]:
            raise RepairBlocked("Every unchanged row requires an explicit disposition")
        evidence = row["evidence"]
        if not evidence or any((item["source_url"], item["source_sha256"]) not in sources or not item["locator"] for item in evidence):
            raise RepairBlocked("Missing exact source hash and locator")
        if fields and not {"manufacturer_pair", "system_price"} <= {item["role"] for item in evidence}:
            raise RepairBlocked("Both model-specific compatibility and commercial kit evidence are required")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def _check_components(product: Any) -> None:
    specs = product.specs
    if not isinstance(specs, dict) or not isinstance(specs.get("__typed_specs", {}), dict):
        raise RepairBlocked(f"Product {product.id}: invalid specification layers")
    typed = specs.get("__typed_specs", {})
    def values(key):
        entry = typed.get(key, {})
        return (specs.get(key), entry.get("value"), entry.get("raw")) if isinstance(entry, dict) else (specs.get(key),)
    def normalized(value):
        return str(value).strip().lower()
    for key in ("includes_indoor_unit", "includes_outdoor_unit"):
        if any(normalized(value) in SPEC_BOOLEAN_FALSE_VALUES for value in values(key)):
            raise RepairBlocked(f"Product {product.id}: explicit component denial")
    count = next((value for value in values("indoor_units_count") if value is not None), None)
    kind = next((value for value in values("type") if value is not None), None)
    if (count is not None and normalized(count) != "1") or normalized(kind) in {"внутренний блок", "наружный блок", "мульти-сплит-система", "мобильный"} or "cat-multi" in {tag.slug for tag in product.tags}:
        raise RepairBlocked(f"Product {product.id}: standalone or multi component evidence")


def build_plan(manifest: dict, products: Iterable[Any], commerce_by_id: dict[int, dict], *, now: datetime | None = None) -> dict:
    validate_manifest(manifest)
    products = list(products)
    by_id = {product.id: product for product in products}
    if len(products) != 217 or by_id.keys() != SCOPE_IDS or commerce_by_id.keys() != SCOPE_IDS:
        raise RepairBlocked("Expected the exact 217 scoped products and commerce states")
    observed, operations, blocked, statuses = [], [], [], set()
    for row in sorted(manifest["products"], key=lambda row: row["identity"]["id"]):
        product = by_id[row["identity"]["id"]]
        if product_identity(product) != row["identity"]:
            raise RepairBlocked(f"Product {product.id}: reviewed identity changed")
        actual = product_projection(product, commerce_by_id[product.id])
        target = {**row["before"], **row["fields_set"]}
        if actual != row["before"] and actual != target:
            raise RepairBlocked(f"Product {product.id}: reviewed product or commercial state changed")
        observed.append({"identity": row["identity"], "state_sha256": digest(actual)})
        if not row["fields_set"]:
            blocked.append({"id": product.id, "reasons": row["blocked_reasons"]})
            continue
        _check_components(product)
        statuses.add("after" if actual == target else "before")
        if actual != target:
            operations.append({"id": product.id, "identity": row["identity"], "before": actual, "target": target,
                               "fields_set": row["fields_set"], "evidence": row["evidence"]})
    if len(statuses) > 1:
        raise RepairBlocked("Partial repair across reviewed candidates; inspect before proceeding")
    changed_ids = [operation["id"] for operation in operations]
    paths = {f"/brands/{quote(by_id[pid].brand.slug, safe='')}/series/{quote(by_id[pid].series.slug, safe='')}/"
             for pid in changed_ids if by_id[pid].series and by_id[pid].brand}
    payload = {
        "ready": True, "issue": 1190, "manifest_sha256": digest(manifest), "sources": manifest["sources"],
        "scoped_product_ids": sorted(SCOPE_IDS), "observed": observed, "operations": operations,
        "changed": len(operations), "product_ids": changed_ids, "blocked_items": blocked,
        "brand_slugs": sorted({by_id[pid].brand.slug for pid in changed_ids if by_id[pid].brand}),
        "series_paths": sorted(paths), "manual_kind_provenance": "unavailable_in_product_schema",
        "manual_review_required": bool(operations),
    }
    payload["state_digest"] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload.update(created_at=now.isoformat(), expires_at=(now + timedelta(minutes=30)).isoformat())
    payload["plan_digest"] = digest(payload)
    return payload
