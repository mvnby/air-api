"""Read-only KingHome source repair plan; execute only a fresh reviewed plan."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.catalog_kinghome_source_repair import (  # noqa: E402
    DEFAULT_MANIFEST, RepairBlocked, build_plan, load_manifest, repaired_specs,
    validate_reviewed_plan,
)


def require_primary(execute: bool, in_recovery: object) -> None:
    if execute and in_recovery is not False:
        raise RepairBlocked("Execute requires a positively verified PostgreSQL primary")


async def run(*, manifest_path: Path, execute: bool = False, reviewed_plan: Path | None = None, execute_plan_digest: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise RepairBlocked("Execute requires --reviewed-plan and --execute-plan-digest")
    if not execute and (reviewed_plan is not None or execute_plan_digest is not None):
        raise RepairBlocked("Review arguments require --execute")
    reviewed = json.loads(reviewed_plan.read_text(encoding="utf-8")) if execute else None

    # Import runtime only after argument/manifest validation. --help never loads DB settings.
    from sqlalchemy import text
    from sqlalchemy.orm.attributes import flag_modified
    from sqlmodel import select
    from core.database import async_session_maker
    from models import Brand, Product, ProductSeries
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService

    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" + ("" if execute else ", READ ONLY")))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        replica = await session.scalar(text("SELECT pg_is_in_recovery()"))
        require_primary(execute, replica)

        # One stable lock order, including rows expected to remain unchanged.
        async def rows(model, condition):
            query = select(model).where(condition).order_by(model.id)
            if execute:
                query = query.with_for_update(of=model)
            return list((await session.execute(query)).scalars())

        brands = await rows(Brand, Brand.id == 4)
        if len(brands) != 1:
            raise RepairBlocked("Reviewed KingHome brand is missing")
        products = await rows(Product, Product.brand_id == 4)
        series = await rows(ProductSeries, ProductSeries.brand_id == 4)
        plan = build_plan(manifest, products, series, brands[0])
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest)
        if not plan["changed"]:
            await session.rollback()
            return {"mode": "execute", "changed": 0, "reviewed_plan_digest": execute_plan_digest, "revision": None}

        product_rows = {obj.id: obj for obj in products}
        series_rows = {obj.id: obj for obj in series}
        product_patches = {row["identity"]["id"]: row for row in manifest["products"]}
        series_patches = {row["identity"]["id"]: row for row in manifest["series"]}
        for operation in plan["operations"]:
            if operation["kind"] == "product":
                obj, patch = product_rows[operation["id"]], product_patches[operation["id"]]
                updated = repaired_specs(obj.specs, patch)
                if updated != obj.specs:
                    obj.specs = updated
                    flag_modified(obj, "specs")
            else:
                obj, patch = series_rows[operation["id"]], series_patches[operation["id"]]
            for key, value in patch["fields_set"].items():
                setattr(obj, key, value)
            session.add(obj)
        revision = await CatalogInvalidationCommitService.commit_global_mutation(
            session, reason="kinghome_source_catalog_repair", product_ids=plan["product_ids"],
            brand_slugs=plan["brand_slugs"], additional_paths=plan["series_paths"],
        )
        return {"mode": "execute", "changed": plan["changed"], "reviewed_plan_digest": execute_plan_digest, "revision": revision}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Apply the complete, exact reviewed plan on the primary")
    parser.add_argument("--reviewed-plan", type=Path, help="Full JSON stdout saved from a plan generated less than 30 minutes ago")
    parser.add_argument("--execute-plan-digest", metavar="SHA256", help="Exact plan_digest from the reviewed JSON")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(manifest_path=args.manifest, execute=args.execute, reviewed_plan=args.reviewed_plan, execute_plan_digest=args.execute_plan_digest))
    except (RepairBlocked, ValueError, KeyError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
