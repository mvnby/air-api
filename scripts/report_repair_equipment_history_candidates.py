import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime
from typing import Iterable, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from scripts.repair_equipment_history_backfill_common import (
    EquipmentCandidateMatch,
    EquipmentFingerprint,
    RepairOrderBackfillContext,
    build_backfill_decision,
    fetch_repair_order_backfill_contexts,
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


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")


def _fmt_fingerprint(fingerprint: EquipmentFingerprint) -> str:
    parts = [
        ("name", fingerprint.equipment_name),
        ("brand", fingerprint.brand),
        ("model", fingerprint.model),
        ("serial", fingerprint.serial),
        ("inventory", fingerprint.inventory_number),
        ("type", fingerprint.equipment_type),
        ("refrigerant", fingerprint.refrigerant_type),
    ]
    rendered = [f"{label}={value}" for label, value in parts if value]
    return ", ".join(rendered) if rendered else "none"


def _fmt_branch(context: RepairOrderBackfillContext) -> str:
    if context.branch is None:
        if context.order.customer_branch_id is None:
            return "unassigned"
        return f"missing branch #{context.order.customer_branch_id}"
    label = context.branch.name or context.branch.delivery_address
    return f"#{context.branch.id} {label}"


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _fmt_candidate(match: EquipmentCandidateMatch) -> str:
    equipment = match.equipment
    conflicts = f" conflicts={','.join(match.conflicts)}" if match.conflicts else ""
    archived = " archived" if equipment.is_archived else ""
    title = equipment.display_name or "unnamed"
    return (
        f"equipment_id={equipment.id} branch={equipment.customer_branch_id or '-'} "
        f"{title!r} confidence={match.confidence} scope={match.branch_scope} "
        f"reasons={','.join(match.reasons)}{conflicts}{archived}"
    )


def _should_print(context: RepairOrderBackfillContext, only_candidates: bool) -> bool:
    if not only_candidates:
        return True
    decision = build_backfill_decision(context)
    return bool(context.candidate_matches) or decision.action in {"create-history", "create-equipment-and-history"}


def _print_context(context: RepairOrderBackfillContext) -> None:
    decision = build_backfill_decision(context)
    order = context.order
    print(f"\n[{context.customer.id}] {context.customer.name}")
    print(f"  branch: {_fmt_branch(context)}")
    print(
        "  order: "
        f"#{order.id} status={_enum_value(order.status)} updated={_fmt_dt(order.updated_at)} "
        f"delivery={order.delivery_address or '-'}"
    )
    print(f"  fingerprint: {_fmt_fingerprint(context.fingerprint)}")
    if context.existing_history:
        history_ids = ", ".join(str(item.id) for item in context.existing_history)
        equipment_ids = ", ".join(str(item.equipment_id) for item in context.existing_history)
        print(f"  existing_history: count={len(context.existing_history)} ids={history_ids} equipment_ids={equipment_ids}")
    else:
        print("  existing_history: none")

    if context.candidate_matches:
        print(f"  candidates: {len(context.candidate_matches)}")
        for match in context.candidate_matches:
            print(f"    - {_fmt_candidate(match)}")
    else:
        print("  candidates: none")

    print(f"  decision: {decision.action} ({decision.reason})")
    if decision.equipment_payload:
        payload = decision.equipment_payload
        print(
            "    auto_create: "
            f"display={payload.get('display_name')!r} "
            f"serial={payload.get('serial') or '-'} "
            f"inventory={payload.get('inventory_number') or '-'} "
            f"branch={payload.get('customer_branch_id')}"
        )


def _decision_counts(contexts: Iterable[RepairOrderBackfillContext]) -> Counter[str]:
    return Counter(build_backfill_decision(context).action for context in contexts)


async def run(
    *,
    customer_ids: Optional[Set[int]],
    max_orders: Optional[int],
    only_candidates: bool,
) -> None:
    engine = create_async_engine(_async_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        contexts = await fetch_repair_order_backfill_contexts(
            session,
            customer_ids=customer_ids,
            max_orders=max_orders,
        )
        printable = [context for context in contexts if _should_print(context, only_candidates)]
        counts = _decision_counts(contexts)

        print("Repair Equipment History Candidate Report")
        print(f"  repair_orders_with_meta={len(contexts)}")
        print(f"  printed_orders={len(printable)}")
        print(f"  only_candidates={only_candidates}")
        if customer_ids:
            print(f"  customer_scope={sorted(customer_ids)}")
        if max_orders is not None:
            print(f"  max_orders={max(0, int(max_orders))}")
        for action, count in sorted(counts.items()):
            print(f"  {action}={count}")

        for context in printable:
            _print_context(context)

        print("\nTips:")
        print("  - Use --only-candidates to hide already-linked and non-actionable orders.")
        print("  - Use scripts/backfill_repair_equipment_history.py for dry-run/apply.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report old repair orders that can be linked to customer equipment history."
    )
    parser.add_argument(
        "--customer-id",
        action="append",
        type=int,
        default=None,
        help="Limit report to a specific customer id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        "--max-orders",
        dest="max_orders",
        type=int,
        default=None,
        help="Limit number of repair orders with repair meta considered.",
    )
    parser.add_argument(
        "--only-candidates",
        action="store_true",
        help="Show only orders with equipment candidates or planned auto-create/history actions.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            customer_ids=_parse_customer_ids(args.customer_id),
            max_orders=args.max_orders,
            only_candidates=args.only_candidates,
        )
    )


if __name__ == "__main__":
    main()
