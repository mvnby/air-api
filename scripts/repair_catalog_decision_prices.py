"""Dry-run the exact approved price-first catalog repair; writes require reviewed digests."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_catalog_decision_sources import run_reviewed_repair  # noqa: E402
from services.catalog_decision_data_repair import RepairBlocked  # noqa: E402
from services.catalog_decision_price_repair import DEFAULT_MANIFEST, apply_operation, build_plan, load_manifest  # noqa: E402


async def run(*, manifest_path: Path = DEFAULT_MANIFEST, execute: bool = False,
              reviewed_plan: Path | None = None, execute_plan_digest: str | None = None,
              manual_kind_review_digest: str | None = None) -> dict:
    return await run_reviewed_repair(
        manifest=load_manifest(manifest_path), plan_builder=build_plan, operation_applier=apply_operation,
        reason="catalog_decision_price_review_1190", execute=execute,
        reviewed_plan=reviewed_plan, execute_plan_digest=execute_plan_digest,
        manual_kind_review_digest=manual_kind_review_digest,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", dest="manifest_path", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed-plan", type=Path)
    parser.add_argument("--execute-plan-digest")
    parser.add_argument("--confirm-manual-kind-review-digest", dest="manual_kind_review_digest")
    try:
        result = asyncio.run(run(**vars(parser.parse_args())))
    except (RepairBlocked, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
