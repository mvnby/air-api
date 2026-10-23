"""Plan a bounded electrical supply correction; writes require a reviewed plan."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.catalog_power_supply_repair import (  # noqa: E402
    DEFAULT_MANIFEST, RepairBlocked, build_plan, load_manifest, repaired_specs,
    validate_reviewed_plan,
)


def require_primary(execute: bool, in_recovery: object) -> None:
    if execute and in_recovery is not False:
        raise RepairBlocked("Execute requires a positively verified PostgreSQL primary")


async def run(*, manifest_path: Path = DEFAULT_MANIFEST, execute: bool = False, reviewed_plan: Path | None = None, execute_plan_digest: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise RepairBlocked("Execute requires --reviewed-plan and --execute-plan-digest")
    if not execute and (reviewed_plan is not None or execute_plan_digest is not None):
        raise RepairBlocked("Review arguments require --execute")
    reviewed = json.loads(reviewed_plan.read_text(encoding="utf-8")) if execute else None

    # --help and argument/manifest failures do not initialize application settings.
    from sqlalchemy import text
    from sqlalchemy.orm.attributes import flag_modified
    from sqlmodel import select
    from core.database import async_session_maker
    from models import Brand, Product
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService

    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" + ("" if execute else ", READ ONLY")))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        require_primary(execute, await session.scalar(text("SELECT pg_is_in_recovery()")))

        async def rows(model, ids):
            query = select(model).where(model.id.in_(sorted(ids))).order_by(model.id)
            if execute:
                query = query.with_for_update(of=model)
            return list((await session.execute(query)).scalars())

        brands = await rows(Brand, {row["id"] for row in manifest["brands"]})
        products = await rows(Product, {row["identity"]["id"] for row in manifest["products"]})
        plan = build_plan(manifest, products, brands)
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest)
        if not plan["changed"]:
            await session.rollback()
            return {"mode": "execute", "changed": 0, "reviewed_plan_digest": execute_plan_digest, "revision": None}

        by_id = {product.id: product for product in products}
        patches = {row["identity"]["id"]: row for row in manifest["products"]}
        for operation in plan["operations"]:
            product = by_id[operation["id"]]
            product.specs = repaired_specs(product.specs, patches[product.id])
            flag_modified(product, "specs")
            session.add(product)
        revision = await CatalogInvalidationCommitService.commit_global_mutation(
            session, reason="catalog_power_supply_repair", product_ids=plan["product_ids"],
            brand_slugs=plan["brand_slugs"],
        )
        return {"mode": "execute", "changed": plan["changed"], "reviewed_plan_digest": execute_plan_digest, "revision": revision}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Apply the exact complete reviewed plan on the primary")
    parser.add_argument("--reviewed-plan", type=Path, help="Full JSON stdout of a plan generated less than 30 minutes ago")
    parser.add_argument("--execute-plan-digest", metavar="SHA256", help="Exact plan_digest in the reviewed JSON")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(
            manifest_path=args.manifest, execute=args.execute,
            reviewed_plan=args.reviewed_plan, execute_plan_digest=args.execute_plan_digest,
        ))
    except (RepairBlocked, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
