"""Backfill legacy Customer/OCR rows with reviewed system ownership."""

from __future__ import annotations

import argparse
import asyncio
import shlex
import sys

sys.path.append(".")

from services.customer_tenant_backfill_service import (  # noqa: E402
    CustomerTenantBackfillBlockedError,
    CustomerTenantBackfillService,
)
from services.tenant_scope_service import TenantScopeResolutionError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assign legacy Customer and requisites-recognition rows to the "
            "reviewed canonical MVN tenant. Dry-run is the default."
        )
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--expected-tenant-id", type=int)
    parser.add_argument("--expected-storefront-id", type=int)
    parser.add_argument("--plan-token")
    return parser


def validate_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if not 1 <= args.limit <= CustomerTenantBackfillService.MAX_LIMIT:
        parser.error("--limit must be between 1 and 1000")
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
            result = await CustomerTenantBackfillService.run(
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
        f"  {label}: total={report['total']} "
        f"legacy_null={report['legacy_null']} "
        f"target_scoped={report['target_scoped']} "
        f"unexpected_scoped={report['unexpected_scoped']} "
        f"unknown_tenant={report['unknown_tenant']}"
    )


def _execute_command(result: dict) -> str:
    return shlex.join(
        [
            "python3",
            "scripts/backfill_customer_tenant_scope.py",
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
    )


def print_result(result: dict) -> None:
    print("Customer Tenant Scope Backfill")
    print(f"  mode={'DRY-RUN' if result['dry_run'] else 'EXECUTE'}")
    print(
        f"  tenant_id={result['tenant_id']} "
        f"storefront_id={result['storefront_id']}"
    )
    print(f"  limit_per_table={result['limit_per_table']}")
    print("  before:")
    _print_report("customer", result["before"]["customer"])
    _print_report("recognition", result["before"]["recognition"])
    print(f"  planned_customer_ids={_ids(result['planned']['customer'])}")
    print(
        "  planned_recognition_ids="
        f"{_ids(result['planned']['recognition'])}"
    )
    print(f"  plan_token={result['plan_token']}")
    print(
        f"  ready_for_backfill="
        f"{str(result['ready_for_backfill']).lower()}"
    )
    for blocker in result["blockers"]:
        print(f"  blocker={blocker}")

    if result["dry_run"]:
        if result["ready_for_backfill"]:
            print("  reviewed_execute_command:")
            print(f"    {_execute_command(result)}")
    else:
        print(
            f"  updated_customers={result['updated']['customer']} "
            f"updated_recognitions={result['updated']['recognition']}"
        )
        print("  after:")
        _print_report("customer", result["after"]["customer"])
        _print_report("recognition", result["after"]["recognition"])
    print(f"  contract_ready={str(result['contract_ready']).lower()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
        print_result(result)
    except (
        CustomerTenantBackfillBlockedError,
        TenantScopeResolutionError,
        ValueError,
    ) as exc:
        print(f"customer_tenant_backfill status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not result["ready_for_backfill"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
