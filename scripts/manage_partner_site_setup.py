"""Plan, then initialize one partner's public settings and detached service prices."""

import argparse
import asyncio
import json
from pathlib import Path
import shlex
import sys

sys.path.append(".")

from services.partner_site_setup_service import (  # noqa: E402
    PartnerSiteSetupManifest, PartnerSiteSetupPlanToken, PartnerSiteSetupService,
)


async def run(args):
    from core.database import async_session_maker

    data = args.manifest.read_bytes()
    if len(data) > 65536:
        raise ValueError("Manifest exceeds 64 KiB")
    manifest = PartnerSiteSetupManifest.model_validate_json(data)
    async with async_session_maker() as session:
        async with session.begin():
            if args.action == "execute":
                return await PartnerSiteSetupService.execute(
                    session, manifest, plan_token=args.plan_token,
                )
            from sqlalchemy import text
            await session.execute(text("SET TRANSACTION READ ONLY"))
            report, _ = await PartnerSiteSetupService.plan(session, manifest)
            token = PartnerSiteSetupPlanToken.issue(plan_digest=report["plan_digest"])
            return {**report, "plan_token_max_age_seconds": 900,
                    "reviewed_execute_command": shlex.join([
                        "python3", "scripts/manage_partner_site_setup.py", "execute",
                        "--manifest", str(args.manifest), "--plan-token", token,
                    ])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "execute"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan-token")
    args = parser.parse_args()
    if (args.action == "execute") != bool(args.plan_token):
        parser.error("Only execute requires --plan-token from a fresh reviewed plan")
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        # No connection strings or credentials in operator output.
        print(f"partner_site_setup status=blocked error_type={type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
