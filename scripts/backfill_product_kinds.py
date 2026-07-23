import argparse
import asyncio
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

sys.path.append(".")

from models import Product
from services.product_kind_service import ProductKindService


@dataclass(frozen=True)
class ProductKindBackfillPlanItem:
    product_id: int
    title: str
    previous_kind: str
    next_kind: str


def build_backfill_plan(
    products: Iterable[Product],
    *,
    repair_conflicts: bool,
) -> list[ProductKindBackfillPlanItem]:
    plan: list[ProductKindBackfillPlanItem] = []
    for product in products:
        next_kind = ProductKindService.derive_from_specs(product.specs)
        previous_kind = str(product.product_kind or "unknown")
        if next_kind == "unknown" or next_kind == previous_kind:
            continue
        if previous_kind != "unknown" and not repair_conflicts:
            continue
        plan.append(
            ProductKindBackfillPlanItem(
                product_id=int(product.id),
                title=product.title,
                previous_kind=previous_kind,
                next_kind=next_kind,
            )
        )
    return plan


def _print_plan(
    plan: Sequence[ProductKindBackfillPlanItem],
    *,
    sample_limit: int,
) -> None:
    transitions = Counter(
        (item.previous_kind, item.next_kind)
        for item in plan
    )
    print("Product Kind Backfill")
    print(f"  planned_changes={len(plan)}")
    for (previous_kind, next_kind), count in sorted(transitions.items()):
        print(f"  {previous_kind} -> {next_kind}: {count}")

    if not plan or sample_limit <= 0:
        return
    print(f"\nSample (up to {sample_limit}):")
    for item in plan[:sample_limit]:
        print(
            f"  [{item.product_id}] {item.previous_kind} -> {item.next_kind}: "
            f"{item.title}"
        )


async def run(
    *,
    execute: bool,
    product_ids: set[int] | None,
    repair_conflicts: bool,
    sample_limit: int,
) -> None:
    from core.config import settings

    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            statement = select(Product).order_by(Product.id.asc())
            if product_ids:
                statement = statement.where(Product.id.in_(product_ids))
            products = list((await session.execute(statement)).scalars().all())
            plan = build_backfill_plan(
                products,
                repair_conflicts=repair_conflicts,
            )
            _print_plan(plan, sample_limit=sample_limit)

            if not plan:
                print("Nothing to backfill.")
                return
            if not execute:
                print("\nDry run only. Use --execute to persist product kinds.")
                return

            products_by_id = {int(product.id): product for product in products}
            for item in plan:
                product = products_by_id[item.product_id]
                product.product_kind = item.next_kind
                session.add(product)
            await session.commit()
            print(f"\nApplied. Updated {len(plan)} products.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill product_kind from canonical specs. "
            "Default mode is dry-run and only fills unknown kinds."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist changes. Without this flag the script only reports the plan.",
    )
    parser.add_argument(
        "--product-id",
        action="append",
        type=int,
        default=None,
        help="Limit the operation to a product id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--repair-conflicts",
        action="store_true",
        help="Also repair known kinds that conflict with canonical specs.type.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=30,
        help="Maximum number of planned products to print (default: 30).",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            execute=args.execute,
            product_ids=set(args.product_id) if args.product_id else None,
            repair_conflicts=args.repair_conflicts,
            sample_limit=max(0, args.sample_limit),
        )
    )


if __name__ == "__main__":
    main()
