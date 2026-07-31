"""Backfill legacy Lead/Order rows with the reviewed server-owned scope.

Dry-run is the default. Execute requires the exact plan token and resolved IDs
printed by a fresh dry-run.
"""

from __future__ import annotations

import argparse
import asyncio
import shlex
import sys

sys.path.append(".")

from services.tenant_scope_backfill_service import (  # noqa: E402
    TenantScopeBackfillBlockedError,
    TenantScopeBackfillService,
)
from services.tenant_scope_service import TenantScopeResolutionError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assign fully legacy-null Lead and Order rows to a reviewed canonical "
            "tenant/storefront scope. Dry-run is the default."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Persist the reviewed batch.")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum rows selected from each table, 1-1000 (default: 100).",
    )
    parser.add_argument("--expected-tenant-id", type=int)
    parser.add_argument("--expected-storefront-id", type=int)
    parser.add_argument("--plan-token")
    return parser


def validate_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if args.limit < TenantScopeBackfillService.MIN_LIMIT:
        parser.error("--limit must be at least 1")
    if args.limit > TenantScopeBackfillService.MAX_LIMIT:
        parser.error("--limit cannot exceed 1000")
    if args.execute:
        missing = [
            flag
            for flag, value in (
                ("--expected-tenant-id", args.expected_tenant_id),
                ("--expected-storefront-id", args.expected_storefront_id),
                ("--plan-token", args.plan_token),
            )
            if value in (None, "")
        ]
        if missing:
            parser.error("--execute requires " + ", ".join(missing))


async def run(args: argparse.Namespace) -> dict:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        try:
            result = await TenantScopeBackfillService.run(
                session,
                execute=args.execute,
                limit_per_table=args.limit,
                expected_tenant_id=args.expected_tenant_id,
                expected_storefront_id=args.expected_storefront_id,
                plan_token=args.plan_token,
            )
            if args.execute:
                await session.commit()
            return result
        except Exception:
            if args.execute:
                await session.rollback()
            raise


def _ids(value: list[int]) -> str:
    return ",".join(str(item) for item in value) or "-"


def _print_report(label: str, report: dict) -> None:
    print(
        f"  {label}: total={report['total']} legacy_null={report['legacy_null']} "
        f"target_scoped={report['target_scoped']} partial={report['partial']} "
        f"unexpected_scoped={report['unexpected_scoped']} "
        f"unknown_tenant={report['unknown_tenant']} "
        f"unknown_storefront={report['unknown_storefront']} "
        f"cross_tenant={report['cross_tenant']}"
    )


def _execute_command(result: dict) -> str:
    command = [
        "python3",
        "scripts/backfill_lead_order_tenant_scope.py",
        "--execute",
        "--limit",
        str(result["limit_per_table"]),
        "--expected-tenant-id",
        str(result["tenant_id"]),
        "--expected-storefront-id",
        str(result["storefront_id"]),
        "--plan-token",
        result["plan_token"],
    ]
    return shlex.join(command)


def print_result(result: dict) -> None:
    print("Lead/Order Tenant Scope Backfill")
    print(f"  mode={'DRY-RUN' if result['dry_run'] else 'EXECUTE'}")
    print(
        f"  scope={result['tenant_slug']}/{result['storefront_slug']} "
        f"tenant_id={result['tenant_id']} storefront_id={result['storefront_id']}"
    )
    print(f"  limit_per_table={result['limit_per_table']}")
    print("  before:")
    _print_report("lead", result["before"]["lead"])
    _print_report("order", result["before"]["order"])
    print(f"  planned_lead_ids={_ids(result['planned']['lead'])}")
    print(f"  planned_order_ids={_ids(result['planned']['order'])}")
    print(f"  plan_token={result['plan_token']}")
    print(f"  ready_for_backfill={str(result['ready_for_backfill']).lower()}")
    for blocker in result["blockers"]:
        print(f"  blocker={blocker}")

    if result["dry_run"]:
        if result["ready_for_backfill"]:
            print("  reviewed_execute_command:")
            print(f"    {_execute_command(result)}")
        print(f"  contract_ready={str(result['contract_ready']).lower()}")
        return

    print(
        f"  updated_leads={result['updated']['lead']} "
        f"updated_orders={result['updated']['order']}"
    )
    print("  after:")
    _print_report("lead", result["after"]["lead"])
    _print_report("order", result["after"]["order"])
    print(f"  contract_ready={str(result['contract_ready']).lower()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
        print_result(result)
    except (
        TenantScopeBackfillBlockedError,
        TenantScopeResolutionError,
        ValueError,
    ) as exc:
        print(f"tenant_scope_backfill status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not result["ready_for_backfill"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
