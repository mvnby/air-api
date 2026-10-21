"""Read-only catalog decision repair plan; execute only an exact reviewed plan."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.catalog_decision_data_repair import (  # noqa: E402
    DEFAULT_MANIFEST, PRODUCT_IDS, RepairBlocked, build_plan, load_manifest,
    validate_reviewed_plan,
)


def require_primary(execute: bool, in_recovery: object) -> None:
    if execute and in_recovery is not False:
        raise RepairBlocked("Execute requires a positively verified PostgreSQL primary")


async def run(*, manifest_path: Path = DEFAULT_MANIFEST, execute: bool = False, reviewed_plan: Path | None = None, execute_plan_digest: str | None = None, manual_kind_review_digest: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise RepairBlocked("Execute requires --reviewed-plan and --execute-plan-digest")
    if not execute and any(value is not None for value in (reviewed_plan, execute_plan_digest, manual_kind_review_digest)):
        raise RepairBlocked("Review arguments require --execute")
    reviewed = json.loads(reviewed_plan.read_text(encoding="utf-8")) if execute else None

    from sqlalchemy import text
    from sqlalchemy.orm import selectinload
    from sqlmodel import select
    from core.database import async_session_maker
    from models import Brand, Product, ProductSeries
    from models.product import ProductTagLink
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService

    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" + ("" if execute else ", READ ONLY")))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        require_primary(execute, await session.scalar(text("SELECT pg_is_in_recovery()")))
        # Lock catalog parents and products in a stable order before loading relations.
        if execute:
            await session.execute(select(Brand).where(Brand.id.in_([3, 4])).order_by(Brand.id).with_for_update())
        query = select(Product).where(Product.id.in_(PRODUCT_IDS)).order_by(Product.id)
        if execute:
            query = query.with_for_update(of=Product)
        products = list((await session.execute(query.options(selectinload(Product.tags), selectinload(Product.brand), selectinload(Product.series)))).scalars())
        if execute:
            series_ids = sorted({product.series_id for product in products if product.series_id is not None})
            await session.execute(select(ProductSeries).where(ProductSeries.id.in_(series_ids)).order_by(ProductSeries.id).with_for_update())
            await session.execute(select(ProductTagLink).where(ProductTagLink.product_id.in_(PRODUCT_IDS)).order_by(ProductTagLink.product_id, ProductTagLink.tag_id).with_for_update())
        plan = build_plan(manifest, products)
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest, manual_kind_review_digest=manual_kind_review_digest)
        if not plan["changed"]:
            await session.rollback()
            return {"mode": "execute", "changed": 0, "reviewed_plan_digest": execute_plan_digest, "revision": None}
        by_id = {product.id: product for product in products}
        for operation in plan["operations"]:
            product = by_id[operation["id"]]
            for key, value in operation["fields_set"].items():
                setattr(product, key, value)
            session.add(product)
        revision = await CatalogInvalidationCommitService.commit_global_mutation(
            session, reason="catalog_decision_reviewed_data_repair", product_ids=plan["product_ids"],
            brand_slugs=plan["brand_slugs"], additional_paths=plan["series_paths"],
        )
        return {"mode": "execute", "changed": plan["changed"], "reviewed_plan_digest": execute_plan_digest, "revision": revision, "blocked_items": plan["blocked_items"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed-plan", type=Path)
    parser.add_argument("--execute-plan-digest", metavar="SHA256")
    parser.add_argument("--confirm-manual-kind-review-digest", dest="manual_kind_review_digest", metavar="SHA256", help="Confirm user-authorized manual review of the legacy kind changes in this exact plan")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(manifest_path=args.manifest, execute=args.execute, reviewed_plan=args.reviewed_plan, execute_plan_digest=args.execute_plan_digest, manual_kind_review_digest=args.manual_kind_review_digest))
    except (RepairBlocked, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
