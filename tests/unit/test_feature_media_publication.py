from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest

from feature_media_publication_test_support import publication_fixture
from services.feature_media_publication import (
    FEATURE_IDS, IMAGE_IDS, PublicationBlocked, build_plan, digest, load_manifest,
    require_primary, validate_manifest, validate_reviewed_plan,
)
from services.general_media_storage_service import LocalGeneralMediaStorage, S3CompatibleGeneralMediaStorage


NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
SCOPE = {"policy": "full_global_catalog", "product_ids": [1, 2, 3]}


def plan(catalog, **kwargs):
    return build_plan(*catalog, storage=LocalGeneralMediaStorage(), affected_scope=SCOPE,
        now=kwargs.get("now", NOW))


def test_plan_is_pure_exact_media_only_and_accepts_frozen_derived():
    catalog = publication_fixture()
    baseline = deepcopy(catalog)
    reviewed = plan(catalog)
    assert catalog == baseline
    assert reviewed["changed"] == 35 and len(reviewed["observed"]) == 35
    assert {op["id"] for op in reviewed["operations"]} == FEATURE_IDS
    assert {op["id"] for op in reviewed["operations"] if "image_media_id" in op["set"]} == IMAGE_IDS
    features = {f.id: f for f in catalog[1]}
    for operation in reviewed["operations"]:
        assert operation["set"].keys() <= {"icon_media_id", "image_media_id", "image_url"}
        for field, value in operation["set"].items():
            setattr(features[operation["id"]], field, value)
    completed = plan(catalog)
    assert completed["changed"] == 0 and completed["operations"] == []
    assert all(f.icon == "legacy-icon-preserved" and f.sort_order == 17 for f in features.values())
    assert {features[id].scope_type for id in (40, 73, 84)} == {"derived"}


@pytest.mark.parametrize("field", ["slug", "scope_type", "brand_id", "icon", "icon_media_id", "image_url", "image_media_id"])
def test_identity_or_any_media_drift_blocks(field):
    catalog = publication_fixture()
    setattr(catalog[1][0], field, 999 if field.endswith("_id") else "drift")
    with pytest.raises(PublicationBlocked, match="drift"):
        plan(catalog)


def test_partial_target_blocks_even_if_each_value_is_individually_reviewed():
    catalog = publication_fixture()
    feature = next(row for row in catalog[1] if row.id in IMAGE_IDS)
    feature.icon_media_id = 10000 + feature.id
    with pytest.raises(PublicationBlocked, match="complete target"):
        plan(catalog)


@pytest.mark.parametrize("missing", ["feature", "asset"])
def test_missing_reviewed_rows_block(missing):
    catalog = publication_fixture()
    catalog[1 if missing == "feature" else 2].pop()
    with pytest.raises(PublicationBlocked):
        plan(catalog)


@pytest.mark.parametrize(("field", "value"), [
    ("kind", "product"), ("processing_status", "failed"), ("variant_type", "card"),
    ("tenant_id", 2), ("storefront_id", 2), ("parent_asset_id", 1),
    ("mime_type", "text/html"), ("content_hash", "0" * 64),
    ("url", "https://foreign.example/asset.svg"),
])
def test_wrong_unready_scoped_or_changed_media_blocks(field, value):
    catalog = publication_fixture()
    setattr(catalog[2][0], field, value)
    with pytest.raises(PublicationBlocked):
        plan(catalog)


def test_external_host_is_rejected_even_when_ref_matches_library_row():
    catalog = publication_fixture()
    catalog[0]["features"][0]["target"]["icon"]["url"] = "https://foreign.example/icon.svg"
    catalog[2][0].url = "https://foreign.example/icon.svg"
    with pytest.raises(PublicationBlocked, match="canonical"):
        plan(catalog)


def test_s3_asset_must_match_configured_canonical_storage_without_io():
    catalog = publication_fixture()
    storage = S3CompatibleGeneralMediaStorage(bucket="test", endpoint_url="https://s3.example",
        public_base_url="https://cdn.example", key_prefix="assets", provider_name="r2")
    for row in catalog[0]["features"]:
        for reference in row["target"].values():
            reference["url"] = storage.build_media_object(content_hash=reference["content_hash"],
                namespace="library", variant_type="original", extension="svg").url
    references = {ref["id"]: ref for row in catalog[0]["features"] for ref in row["target"].values()}
    for asset in catalog[2]:
        asset.storage_provider, asset.url = "r2", references[asset.id]["url"]
    assert build_plan(*catalog, storage=storage, affected_scope=SCOPE, now=NOW)["changed"] == 35
    catalog[2][0].url = catalog[0]["features"][0]["target"]["icon"]["url"] = "https://other.example/icon.svg"
    with pytest.raises(PublicationBlocked, match="canonical"):
        build_plan(*catalog, storage=storage, affected_scope=SCOPE, now=NOW)


@pytest.mark.parametrize("fault", ["duplicate", "slug_duplicate", "extra", "missing", "field", "missing_guard", "target_icon", "hero_scope", "unknown_identity", "hash", "bool_id"])
def test_manifest_rejects_ambiguous_or_widened_input(fault):
    manifest = publication_fixture()[0]
    row = manifest["features"][0]
    if fault == "duplicate":
        manifest["features"][1] = deepcopy(row)
    elif fault == "slug_duplicate":
        manifest["features"][1]["identity"]["slug"] = row["identity"]["slug"]
    elif fault == "extra":
        manifest["features"].append(deepcopy(row))
    elif fault == "missing":
        manifest["features"].pop()
    elif fault == "field":
        row["target"]["description"] = "forbidden"
    elif fault == "missing_guard":
        del row["before"]["icon"]
    elif fault == "target_icon":
        row["target"]["icon"] = "raw-url"
    elif fault == "hero_scope":
        row["target"]["image"] = deepcopy(row["target"]["icon"])
    elif fault == "unknown_identity":
        row["identity"]["name"] = "forbidden"
    elif fault == "hash":
        row["target"]["icon"]["content_hash"] = "not-hash"
    else:
        row["identity"]["id"] = True
    with pytest.raises(ValueError):
        validate_manifest(manifest)


def test_loader_rejects_duplicate_json_keys(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"schema_version":1,"schema_version":1,"features":[]}', encoding="utf-8")
    with pytest.raises(PublicationBlocked, match="Duplicate JSON key"):
        load_manifest(manifest)


def test_exact_digest_window_and_live_state_are_required():
    catalog = publication_fixture()
    reviewed = plan(catalog)
    live = plan(catalog, now=NOW + timedelta(minutes=1))
    validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=NOW + timedelta(minutes=1))
    with pytest.raises(PublicationBlocked, match="digest"):
        validate_reviewed_plan(reviewed, live, "0" * 64, now=NOW)
    for when in (NOW - timedelta(seconds=1), NOW + timedelta(minutes=30)):
        with pytest.raises(PublicationBlocked, match="expired"):
            validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=when)
    forged = deepcopy(reviewed)
    forged["operations"] = []
    with pytest.raises(PublicationBlocked, match="digest"):
        validate_reviewed_plan(forged, live, reviewed["plan_digest"], now=NOW)
    forged["plan_digest"] = digest({k: v for k, v in forged.items() if k != "plan_digest"})
    # Even a recomputed reviewed hash cannot authorize operations absent in the live plan.
    with pytest.raises(PublicationBlocked):
        validate_reviewed_plan(forged, live, forged["plan_digest"], now=NOW)


def test_affected_scope_change_blocks_a_previously_reviewed_plan():
    catalog = publication_fixture()
    reviewed = plan(catalog)
    changed = build_plan(*catalog, storage=LocalGeneralMediaStorage(),
        affected_scope={**SCOPE, "product_ids": [1, 2, 3, 4]}, now=NOW)
    with pytest.raises(PublicationBlocked, match="changed since review"):
        validate_reviewed_plan(reviewed, changed, reviewed["plan_digest"], now=NOW)


@pytest.mark.parametrize("value", [True, None, 0, "false"])
def test_execution_requires_positive_primary_verification(value):
    with pytest.raises(PublicationBlocked, match="primary"):
        require_primary(value)
    require_primary(False)
