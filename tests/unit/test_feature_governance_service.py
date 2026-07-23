import copy
from pathlib import Path

from services.feature_governance_service import (
    FeatureGovernanceService,
    load_feature_governance_registry,
)
from services.tcl_feature_canary_service import load_tcl_feature_canary_manifest


ROOT = Path(__file__).parents[2]
REGISTRY = ROOT / "data/features/universal_v1.json"
TCL_MANIFEST = ROOT / "data/feature_canary/tcl_2026.json"


def test_universal_feature_registry_is_valid_and_tcl_manifest_conforms():
    registry = load_feature_governance_registry(REGISTRY)
    manifest = load_tcl_feature_canary_manifest(TCL_MANIFEST)

    report = FeatureGovernanceService.audit_manifest(registry, manifest)

    assert report["summary"] == {
        "categories": 9,
        "canonical_features": 20,
        "manifest_active_features": 11,
        "errors": 0,
        "warnings": 0,
    }
    assert report["findings"] == []


def test_governance_audit_detects_category_scope_duplicate_and_width_issues():
    registry = load_feature_governance_registry(REGISTRY)
    manifest = load_tcl_feature_canary_manifest(TCL_MANIFEST)
    broken = copy.deepcopy(manifest)
    broken["features"].append(
        {
            "slug": "smart-inverter-copy",
            "name": "Smart Inverter",
            "category_slug": "comfort",
            "scope_type": "brand",
            "brand_slug": "tcl",
            "aliases": [],
        }
    )
    built_in = next(item for item in broken["features"] if item["slug"] == "vstroennyi-wi-fi")
    built_in["brand_slug"] = "tcl"
    all_series = list(broken["series_allowlist"])
    for series_slug in all_series:
        broken["series_links"].setdefault(series_slug, []).append("smart-inverter-copy")

    report = FeatureGovernanceService.audit_manifest(registry, broken)
    codes = {item["code"] for item in report["findings"]}

    assert "category_mismatch" in codes
    assert "universal_feature_brand_restricted" in codes
    assert "suspected_duplicate" in codes
    assert "possibly_too_broad_assignment" in codes


def test_registry_validation_rejects_alias_collision():
    registry = load_feature_governance_registry(REGISTRY)
    broken = copy.deepcopy(registry)
    broken["features"][1]["aliases"].append("Inverter")

    findings = FeatureGovernanceService.validate_registry(broken)

    assert any(item["code"] == "alias_collision" for item in findings)
