"""Create only the reviewed domainless training-kitlane cabinet, with no credentials or sending."""

import argparse
import asyncio
import json
import shlex
import sys

sys.path.append(".")

from services.tenant_training_bootstrap_service import (  # noqa: E402
    TenantTrainingBootstrapService, TenantTrainingBootstrapToken,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "execute"), nargs="?", default="plan")
    parser.add_argument("--product-id", type=int, action="append", required=True)
    parser.add_argument("--plan-token")
    args = parser.parse_args(argv)
    if (args.action == "execute") != bool(args.plan_token):
        parser.error("Only execute requires --plan-token from a fresh reviewed plan")
    if len(args.product_id) != 2 or len(set(args.product_id)) != 2 or min(args.product_id) <= 0:
        parser.error("Exactly two distinct positive --product-id values are required")
    return args


async def run(args):
    from core.database import async_session_maker
    from sqlalchemy import text
    async with async_session_maker() as session:
        async with session.begin():
            if args.action == "execute":
                return await TenantTrainingBootstrapService.execute(session,
                    product_ids=args.product_id, plan_token=args.plan_token)
            await session.execute(text("SET TRANSACTION READ ONLY"))
            report = await TenantTrainingBootstrapService.plan(session, product_ids=args.product_id)
            if not report["blockers"]:
                report["reviewed_execute_command"] = shlex.join([
                    "python3", "scripts/bootstrap_private_training.py", "execute",
                    "--product-id", str(args.product_id[0]), "--product-id", str(args.product_id[1]),
                    "--plan-token", TenantTrainingBootstrapToken.issue(plan_digest=report["plan_digest"]),
                ])
                report["plan_token_max_age_seconds"] = TenantTrainingBootstrapToken.MAX_AGE_SECONDS
            return report


def main():
    try:
        report = asyncio.run(run(parse_args()))
    except Exception as exc:
        print(f"private_training_bootstrap status=blocked error_type={type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
