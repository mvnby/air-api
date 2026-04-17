import argparse
import asyncio
import sys
from datetime import datetime
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from scripts.customer_branch_backfill_common import (
    CustomerAddressStat,
    build_backfill_plan,
    fetch_customer_address_stats,
    fetch_existing_branch_keys,
    filter_stats_by_min_orders,
)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")


def _print_customer_block(
    *,
    customer_id: int,
    customer_name: str,
    stats: List[CustomerAddressStat],
    existing_count: int,
) -> None:
    print(f"\n[{customer_id}] {customer_name}")
    print(f"  existing_branches={existing_count}")
    for stat in stats:
        print(
            "  - "
            f"orders={stat.order_count:<3} "
            f"linked={stat.linked_order_count:<3} "
            f"first={_fmt_dt(stat.first_order_at)} "
            f"last={_fmt_dt(stat.last_order_at)} "
            f"address={stat.normalized_address}"
        )


async def run(*, min_orders: int, only_candidates: bool, max_customers: int | None) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        all_stats_by_customer = await fetch_customer_address_stats(session)
        filtered_stats_by_customer = filter_stats_by_min_orders(
            all_stats_by_customer,
            min_orders=min_orders,
        )
        existing_branches_by_customer = await fetch_existing_branch_keys(session)
        plan = build_backfill_plan(
            stats_by_customer=filtered_stats_by_customer,
            existing_branches_by_customer=existing_branches_by_customer,
        )

        customers_with_candidates = {item.customer_id for item in plan}
        customer_ids = sorted(filtered_stats_by_customer.keys())
        if only_candidates:
            customer_ids = [customer_id for customer_id in customer_ids if customer_id in customers_with_candidates]
        if max_customers is not None:
            customer_ids = customer_ids[: max(0, max_customers)]

        plan_count_by_customer: Dict[int, int] = {}
        for item in plan:
            plan_count_by_customer[item.customer_id] = plan_count_by_customer.get(item.customer_id, 0) + 1

        print("Customer Branch Backfill Report")
        print(f"  total_customers_with_addresses={len(all_stats_by_customer)}")
        print(f"  customers_after_min_orders_filter={len(filtered_stats_by_customer)}")
        print(f"  min_orders={max(1, min_orders)}")
        print(f"  customers_with_new_branch_candidates={len(customers_with_candidates)}")
        print(f"  new_branch_candidates_total={len(plan)}")
        print(f"  printed_customers={len(customer_ids)}")

        for customer_id in customer_ids:
            stats = filtered_stats_by_customer.get(customer_id, [])
            if not stats:
                continue
            customer_name = stats[0].customer_name
            existing_count = len(existing_branches_by_customer.get(customer_id, {}))
            _print_customer_block(
                customer_id=customer_id,
                customer_name=customer_name,
                stats=stats,
                existing_count=existing_count,
            )
            new_count = plan_count_by_customer.get(customer_id, 0)
            if new_count:
                print(f"    -> new_branch_candidates={new_count}")

        print("\nTips:")
        print("  - Use --only-candidates to focus only on customers with pending branch creation.")
        print("  - Use scripts/backfill_customer_branches.py for dry-run/apply.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Report customer branch candidates from order delivery addresses.")
    parser.add_argument(
        "--min-orders",
        type=int,
        default=2,
        help="Minimum number of orders per address to include candidate (default: 2).",
    )
    parser.add_argument(
        "--only-candidates",
        action="store_true",
        help="Show only customers that still have new branch candidates.",
    )
    parser.add_argument(
        "--max-customers",
        type=int,
        default=None,
        help="Limit number of customers printed in report.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            min_orders=args.min_orders,
            only_candidates=args.only_candidates,
            max_customers=args.max_customers,
        )
    )


if __name__ == "__main__":
    main()
