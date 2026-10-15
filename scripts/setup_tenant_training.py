"""Plan an additive editable teaching fixture in an explicitly private training tenant."""

import argparse
import asyncio
import json
import shlex
import sys

sys.path.append(".")

from services.tenant_training_setup_service import (  # noqa: E402
    TenantTrainingPlanToken, TenantTrainingSetupService,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "execute"), nargs="?", default="plan")
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--storefront-id", type=int, required=True)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--plan-token")
    args = parser.parse_args(argv)
    if (args.action == "execute") != bool(args.plan_token):
        parser.error("Only execute requires --plan-token from a fresh reviewed plan")
    return args


async def run(args):
    from core.database import async_session_maker
    from sqlalchemy import text

    target = dict(tenant_id=args.tenant_id, storefront_id=args.storefront_id, tenant_slug=args.tenant_slug)
    async with async_session_maker() as session:
        async with session.begin():
            if args.action == "execute":
                return await TenantTrainingSetupService.execute(session, **target, plan_token=args.plan_token)
            await session.execute(text("SET TRANSACTION READ ONLY"))
            report = await TenantTrainingSetupService.plan(session, **target)
            if not report["blockers"]:
                token = TenantTrainingPlanToken.issue(plan_digest=report["plan_digest"])
                report["reviewed_execute_command"] = shlex.join([
                    "python3", "scripts/setup_tenant_training.py", "execute",
                    "--tenant-id", str(args.tenant_id), "--storefront-id", str(args.storefront_id),
                    "--tenant-slug", args.tenant_slug, "--plan-token", token,
                ])
                report["plan_token_max_age_seconds"] = TenantTrainingPlanToken.MAX_AGE_SECONDS
            return report


def main():
    try:
        result = asyncio.run(run(parse_args()))
    except Exception as exc:
        print(f"tenant_training_setup status=blocked error_type={type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
