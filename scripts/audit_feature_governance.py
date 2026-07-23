import argparse
import json
import sys
from pathlib import Path

sys.path.append(".")

from services.feature_governance_service import (
    FeatureGovernanceService,
    load_feature_governance_registry,
)
from services.tcl_feature_canary_service import load_tcl_feature_canary_manifest


DEFAULT_REGISTRY = Path("data/features/universal_v1.json")
DEFAULT_MANIFEST = Path("data/feature_canary/tcl_2026.json")


def run(*, registry_path: Path, manifest_path: Path) -> dict:
    registry = load_feature_governance_registry(registry_path)
    manifest = load_tcl_feature_canary_manifest(manifest_path)
    return FeatureGovernanceService.audit_manifest(registry, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Feature taxonomy and a catalog manifest")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when errors are found")
    args = parser.parse_args()

    report = run(registry_path=args.registry, manifest_path=args.manifest)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.strict and report["summary"]["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
