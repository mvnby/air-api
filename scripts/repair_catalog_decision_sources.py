"""Dry-run the exact issue-1190 source repair; execution needs a fresh reviewed digest."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_catalog_decision_data import require_primary  # noqa: E402
from services.catalog_decision_data_repair import RepairBlocked, validate_reviewed_plan  # noqa: E402
from services.catalog_decision_source_repair import (  # noqa: E402
    DEFAULT_MANIFEST, SCOPE_IDS, SUPPLIER_KEYS, build_plan, commerce_projection, load_manifest,
)


async def run(*, manifest_path: Path = DEFAULT_MANIFEST, execute: bool = False,
              reviewed_plan: Path | None = None, execute_plan_digest: str | None = None,
              manual_kind_review_digest: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise RepairBlocked("Execute requires --reviewed-plan and --execute-plan-digest")
    if not execute and any(value is not None for value in (reviewed_plan, execute_plan_digest, manual_kind_review_digest)):
        raise RepairBlocked("Review arguments require --execute")
    reviewed = json.loads(reviewed_plan.read_text(encoding="utf-8")) if execute else None

    from sqlalchemy import text, tuple_
    from sqlalchemy.orm import selectinload
    from sqlmodel import select
    from core.database import async_session_maker
    from models import Brand, Product, ProductSeries, Tag
    from models.product import ProductTagLink
    from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource
    from services.catalog_decision_projection import CatalogDecisionQueryService
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService

    def columns(obj):
        return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}

    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" + ("" if execute else ", READ ONLY")))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        require_primary(execute, await session.scalar(text("SELECT pg_is_in_recovery()")))

        async def rows(query):
            if execute:
                query = query.with_for_update()
            return list((await session.execute(query)).scalars())

        # Parent FOR UPDATE locks also fence insertion of new FK children.
        supplier_ids = manifest["scope_supplier_ids"]
        suppliers = await rows(select(Supplier).where(Supplier.id.in_(supplier_ids)).order_by(Supplier.id))
        if execute:
            await rows(select(Brand).where(Brand.id.in_({row["identity"]["brand_id"] for row in manifest["products"]})).order_by(Brand.id))
        query = select(Product).where(Product.id.in_(SCOPE_IDS)).order_by(Product.id)
        if execute:
            query = query.with_for_update(of=Product)
        products = list((await session.execute(query.options(selectinload(Product.tags), selectinload(Product.brand), selectinload(Product.series)))).scalars())
        if execute:
            await rows(select(ProductSeries).where(ProductSeries.id.in_({p.series_id for p in products if p.series_id is not None})).order_by(ProductSeries.id))
            await rows(select(Tag).where(Tag.id.in_({tag.id for product in products for tag in product.tags})).order_by(Tag.id))
            await rows(select(ProductTagLink).where(ProductTagLink.product_id.in_(SCOPE_IDS)).order_by(ProductTagLink.product_id, ProductTagLink.tag_id))
        mappings = await rows(select(ProductSupplierMapping).where(ProductSupplierMapping.product_id.in_(SCOPE_IDS)).order_by(ProductSupplierMapping.id))
        if any(mapping.supplier_id not in supplier_ids for mapping in mappings):
            raise RepairBlocked("Scoped supplier mapping changed")
        keys = [(row.supplier_id, row.external_id) for row in mappings]
        offers = await rows(select(SupplierOffer).where(tuple_(SupplierOffer.supplier_id, SupplierOffer.external_id).in_(keys)).order_by(SupplierOffer.id))
        stocks = await rows(select(ProductLocalStock).where(ProductLocalStock.product_id.in_(SCOPE_IDS)).order_by(ProductLocalStock.id))
        sources = await rows(select(SupplierPriceSource).where(SupplierPriceSource.supplier_id.in_(supplier_ids)).order_by(SupplierPriceSource.id))
        supplier_by_id = {s.id: {key: getattr(s, key) for key in SUPPLIER_KEYS} for s in suppliers}
        offer_by_key = {(o.supplier_id, o.external_id): columns(o) for o in offers}
        commerce = {
            product.id: commerce_projection({
                "supplier_mappings": [{**columns(m), "supplier": supplier_by_id[m.supplier_id],
                                       "offer": offer_by_key.get((m.supplier_id, m.external_id))}
                                      for m in mappings if m.product_id == product.id],
                "local_stocks": [columns(stock) for stock in stocks if stock.product_id == product.id],
            }, [columns(source) for source in sources]) for product in products
        }
        plan = build_plan(manifest, products, commerce)
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest, manual_kind_review_digest=manual_kind_review_digest)
        if not plan["changed"]:
            await session.rollback()
            return {"mode": "execute", "changed": 0, "reviewed_plan_digest": execute_plan_digest, "revision": None}
        by_id = {product.id: product for product in products}
        for operation in plan["operations"]:
            by_id[operation["id"]].product_kind = operation["fields_set"]["product_kind"]
            session.add(by_id[operation["id"]])
        await session.flush()
        eligible = await CatalogDecisionQueryService.eligible_system_product_ids(session, plan["product_ids"])
        if eligible != set(plan["product_ids"]):
            raise RepairBlocked("A reviewed target contradicts strict catalog eligibility")
        revision = await CatalogInvalidationCommitService.commit_global_mutation(
            session, reason="catalog_decision_source_review_1190", product_ids=plan["product_ids"],
            brand_slugs=plan["brand_slugs"], additional_paths=plan["series_paths"],
        )
        return {"mode": "execute", "changed": plan["changed"], "revision": revision,
                "reviewed_plan_digest": execute_plan_digest, "blocked_items": plan["blocked_items"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", dest="manifest_path", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed-plan", type=Path)
    parser.add_argument("--execute-plan-digest")
    parser.add_argument("--confirm-manual-kind-review-digest", dest="manual_kind_review_digest")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(**vars(args)))
    except (RepairBlocked, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
