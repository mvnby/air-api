"""Apply a reviewed canonical product-area plan.

The default mode is dry-run. The command only writes missing ``specs.area_m2``
values from an explicitly reviewed JSON plan and never overwrites existing data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

sys.path.append(".")

from services.catalog_area_backfill import (  # noqa: E402
    CONFIDENCE_RANK,
    CatalogAreaPlanEntry,
    build_specs_update,
    load_plan_entries,
    should_apply,
)


DEFAULT_PLAN_PATH = "data/catalog_area_backfill_plan_2026-07-19.json"


def _model_matches_product(product: Any, entry: CatalogAreaPlanEntry) -> bool:
    model = "".join(char for char in entry.model.casefold() if char.isalnum())
    title = "".join(char for char in product.title.casefold() if char.isalnum())
    return model in title


def load_plan(path: str) -> list[CatalogAreaPlanEntry]:
    with Path(path).open(encoding="utf-8") as plan_file:
        return load_plan_entries(json.load(plan_file))


async def run(*, execute: bool, minimum_confidence: str, plan_path: str) -> dict[str, Any]:
    from core.database import async_session_maker
    from models import Product

    entries = load_plan(plan_path)
    candidate_entries = [entry for entry in entries if should_apply(entry, minimum_confidence)]
    entries_by_id = {entry.product_id: entry for entry in candidate_entries}
    result: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "minimum_confidence": minimum_confidence,
        "plan_path": plan_path,
        "plan_entries": len(entries),
        "eligible_candidates": len(candidate_entries),
        "not_applicable": sum(entry.status == "not_applicable" for entry in entries),
        "insufficient_data": sum(entry.status == "insufficient_data" for entry in entries),
        "updated": [],
        "skipped_existing_area": [],
        "skipped_model_mismatch": [],
        "missing_products": [],
    }
    if not entries_by_id:
        return result

    async with async_session_maker() as session:
        products = (
            await session.execute(select(Product).where(Product.id.in_(entries_by_id)).order_by(Product.id))
        ).scalars().all()
        found_ids = {product.id for product in products}
        result["missing_products"] = sorted(set(entries_by_id) - found_ids)

        for product in products:
            entry = entries_by_id[product.id]
            if not _model_matches_product(product, entry):
                result["skipped_model_mismatch"].append(product.id)
                continue
            updated_specs = build_specs_update(product.specs, entry)
            if updated_specs is None:
                result["skipped_existing_area"].append(product.id)
                continue
            result["updated"].append(
                {
                    "product_id": product.id,
                    "model": entry.model,
                    "area_m2": entry.proposed_area_m2,
                    "confidence": entry.confidence,
                }
            )
            if execute:
                product.specs = updated_specs
                flag_modified(product, "specs")
                session.add(product)

        if execute:
            await session.commit()
        else:
            await session.rollback()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill reviewed missing specs.area_m2 values.")
    parser.add_argument("--execute", action="store_true", help="Persist planned updates.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode (the default).")
    parser.add_argument("--plan", default=DEFAULT_PLAN_PATH, help="Reviewed JSON plan path.")
    parser.add_argument(
        "--min-confidence",
        choices=tuple(CONFIDENCE_RANK),
        default="high",
        help="Only apply candidates at or above this confidence (default: high).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run cannot be used together")
    result = asyncio.run(
        run(
            execute=args.execute and not args.dry_run,
            minimum_confidence=args.min_confidence,
            plan_path=args.plan,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
