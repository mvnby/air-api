import argparse
import asyncio
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import CustomerBranch
from scripts.customer_branch_backfill_common import (
    BranchBackfillPlanItem,
    build_backfill_plan,
    fetch_customer_address_stats,
    fetch_existing_branch_keys,
    filter_stats_by_min_orders,
)


def _parse_customer_ids(raw_values: Optional[List[int]]) -> Optional[Set[int]]:
    if not raw_values:
        return None
    return {int(value) for value in raw_values if int(value) > 0}


def _print_plan(plan: Iterable[BranchBackfillPlanItem]) -> None:
    grouped: Dict[int, List[BranchBackfillPlanItem]] = defaultdict(list)
    for item in plan:
        grouped[item.customer_id].append(item)

    for customer_id in sorted(grouped.keys()):
        entries = grouped[customer_id]
        customer_name = entries[0].customer_name
        print(f"\n[{customer_id}] {customer_name}")
        for entry in entries:
            default_mark = " default" if entry.is_default else ""
            print(
                "  - "
                f"orders={entry.order_count:<3} linked={entry.linked_order_count:<3} "
                f"address={entry.delivery_address}{default_mark}"
            )


async def run(*, execute: bool, min_orders: int, customer_ids: Optional[Set[int]]) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        stats_by_customer = await fetch_customer_address_stats(session)
        stats_by_customer = filter_stats_by_min_orders(stats_by_customer, min_orders=min_orders)
        existing_branches_by_customer = await fetch_existing_branch_keys(session)

        if customer_ids:
            stats_by_customer = {
                customer_id: stats
                for customer_id, stats in stats_by_customer.items()
                if customer_id in customer_ids
            }
            existing_branches_by_customer = {
                customer_id: entries
                for customer_id, entries in existing_branches_by_customer.items()
                if customer_id in customer_ids
            }

        plan = build_backfill_plan(
            stats_by_customer=stats_by_customer,
            existing_branches_by_customer=existing_branches_by_customer,
        )

        print("Customer Branch Backfill")
        print(f"  min_orders={max(1, min_orders)}")
        print(f"  scoped_customers={len(stats_by_customer)}")
        print(f"  new_branches_planned={len(plan)}")
        if customer_ids:
            print(f"  customer_scope={sorted(customer_ids)}")

        if not plan:
            print("Nothing to backfill.")
            await engine.dispose()
            return

        _print_plan(plan)

        if not execute:
            print("\nDry run only. Use --execute to persist branches.")
            await engine.dispose()
            return

        for item in plan:
            branch = CustomerBranch(
                customer_id=item.customer_id,
                delivery_address=item.delivery_address,
                is_default=item.is_default,
            )
            session.add(branch)

        await session.commit()
        print(f"\nApplied. Created {len(plan)} customer branches.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create missing customer branches from historical order delivery addresses. "
            "Default mode is dry-run."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist changes. Without this flag script only prints planned actions.",
    )
    parser.add_argument(
        "--min-orders",
        type=int,
        default=2,
        help="Minimum number of orders per address to consider branch candidate (default: 2).",
    )
    parser.add_argument(
        "--customer-id",
        action="append",
        type=int,
        default=None,
        help="Limit backfill to specific customer id. Can be passed multiple times.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            execute=args.execute,
            min_orders=args.min_orders,
            customer_ids=_parse_customer_ids(args.customer_id),
        )
    )


if __name__ == "__main__":
    main()
