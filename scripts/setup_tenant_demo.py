"""Plan by default, then provision one reviewed synthetic read-only tenant demo."""

import argparse
import asyncio
import json
import shlex
import sys

sys.path.append(".")

from services.tenant_demo_setup_service import (  # noqa: E402
    TenantDemoSetupPlanToken,
    TenantDemoSetupService,
)


async def run(args: argparse.Namespace) -> dict:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        async with session.begin():
            if args.action == "execute":
                return await TenantDemoSetupService.execute(
                    session,
                    tenant_id=args.tenant_id,
                    storefront_id=args.storefront_id,
                    plan_token=args.plan_token,
                )
            from sqlalchemy import text

            await session.execute(text("SET TRANSACTION READ ONLY"))
            report = await TenantDemoSetupService.plan(
                session,
                tenant_id=args.tenant_id,
                storefront_id=args.storefront_id,
            )
            token = TenantDemoSetupPlanToken.issue(
                plan_digest=report["plan_digest"]
            )
            return {
                **report,
                "plan_token_max_age_seconds": (
                    TenantDemoSetupPlanToken.MAX_AGE_SECONDS
                ),
                "reviewed_execute_command": shlex.join(
                    [
                        "python3",
                        "scripts/setup_tenant_demo.py",
                        "execute",
                        "--tenant-id",
                        str(args.tenant_id),
                        "--storefront-id",
                        str(args.storefront_id),
                        "--plan-token",
                        token,
                    ]
                ),
            }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "execute"), nargs="?", default="plan")
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--storefront-id", type=int, required=True)
    parser.add_argument("--plan-token")
    args = parser.parse_args(argv)
    if (args.action == "execute") != bool(args.plan_token):
        parser.error("Only execute requires --plan-token from a fresh reviewed plan")
    return args


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        print(
            f"tenant_demo_setup status=blocked error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
