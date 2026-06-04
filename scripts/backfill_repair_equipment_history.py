import argparse
import asyncio
import sys
from typing import List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from scripts.repair_equipment_history_backfill_common import (
    BackfillApplyResult,
    apply_backfill_contexts,
    fetch_repair_order_backfill_contexts,
    summarize_results,
)


def _parse_customer_ids(raw_values: Optional[List[int]]) -> Optional[Set[int]]:
    if not raw_values:
        return None
    return {int(value) for value in raw_values if int(value) > 0}


def _async_database_url() -> str:
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql+psycopg://"):
        return db_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return db_url


def _print_result(result: BackfillApplyResult) -> None:
    target = f" equipment_id={result.equipment_id}" if result.equipment_id is not None else ""
    history = f" history_id={result.history_id}" if result.history_id is not None else ""
    mode = "applied" if result.executed else "planned"
    print(f"  - order_id={result.order_id} {mode} action={result.action}{target}{history} reason={result.reason}")


async def run(
    *,
    execute: bool,
    customer_ids: Optional[Set[int]],
    max_orders: Optional[int],
) -> None:
    engine = create_async_engine(_async_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        contexts = await fetch_repair_order_backfill_contexts(
            session,
            customer_ids=customer_ids,
            max_orders=max_orders,
        )
        results = await apply_backfill_contexts(session, contexts, execute=execute)
        counts = summarize_results(results)

        print("Repair Equipment History Backfill")
        print(f"  mode={'execute' if execute else 'dry-run'}")
        print(f"  repair_orders_with_meta={len(contexts)}")
        if customer_ids:
            print(f"  customer_scope={sorted(customer_ids)}")
        if max_orders is not None:
            print(f"  max_orders={max(0, int(max_orders))}")
        for action, count in sorted(counts.items()):
            print(f"  {action}={count}")

        if not results:
            print("Nothing to backfill.")
        else:
            print("\nPlan:")
            for result in results:
                _print_result(result)

        if not execute:
            print("\nDry run only. Use --execute to persist safe history records.")
        else:
            created_history = sum(1 for result in results if result.executed and result.history_id is not None)
            created_equipment = sum(
                1 for result in results if result.executed and result.action == "create-equipment-and-history"
            )
            print(f"\nApplied. Created {created_history} history records and {created_equipment} equipment records.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill customer equipment service history from old repair orders. "
            "Default mode is dry-run."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist safe changes. Without this flag script only prints planned actions.",
    )
    parser.add_argument(
        "--customer-id",
        action="append",
        type=int,
        default=None,
        help="Limit backfill to a specific customer id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        "--max-orders",
        dest="max_orders",
        type=int,
        default=None,
        help="Limit number of repair orders with repair meta considered.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            execute=args.execute,
            customer_ids=_parse_customer_ids(args.customer_id),
            max_orders=args.max_orders,
        )
    )


if __name__ == "__main__":
    main()
