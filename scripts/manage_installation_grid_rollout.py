"""Plan or atomically apply the reviewed installation grid to exact tenant scopes."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from services.installation_grid_rollout import (  # noqa: E402
    InstallationGridPlanToken, InstallationGridRolloutService,
)


def _execute_command(args: argparse.Namespace, token: str) -> str:
    parts = ["python3", "scripts/manage_installation_grid_rollout.py", "apply"]
    for slug in args.expected_partner:
        parts.extend(("--expected-partner", slug))
    for option, value in (
        ("--backend-release-commit", args.backend_release_commit),
        ("--backend-image-digest", args.backend_image_digest),
        ("--web-v2-commit", args.web_v2_commit),
        ("--web-v2-proof", args.web_v2_proof),
        ("--manager-editor-proof", args.manager_editor_proof),
        ("--legacy-list-proof", args.legacy_list_proof),
        ("--legacy-calculate-proof", args.legacy_calculate_proof),
        ("--legacy-tariff-calculate-proof", args.legacy_tariff_calculate_proof),
    ):
        if value:
            parts.extend((option, value))
    if args.include_demo_reset:
        parts.append("--include-demo-reset")
    parts.extend(("--plan-token", token))
    return shlex.join(parts)


async def run(args: argparse.Namespace) -> dict:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        async with session.begin():
            if args.action == "plan":
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                await session.execute(text("SET TRANSACTION READ ONLY"))
                report, _ = await InstallationGridRolloutService.plan(
                    session, expected_partner_slugs=tuple(args.expected_partner),
                    backend_release_commit=args.backend_release_commit,
                    backend_image_digest=args.backend_image_digest,
                    web_v2_commit=args.web_v2_commit,
                    web_v2_proof=args.web_v2_proof,
                    manager_editor_proof=args.manager_editor_proof,
                    legacy_list_proof=args.legacy_list_proof,
                    legacy_calculate_proof=args.legacy_calculate_proof,
                    legacy_tariff_calculate_proof=args.legacy_tariff_calculate_proof,
                    include_demo_reset=args.include_demo_reset,
                )
                if report["blockers"]:
                    return report
                token = InstallationGridPlanToken.issue(
                    plan_digest=report["plan_digest"],
                )
                return {**report, "plan_token_max_age_seconds": 900,
                        "reviewed_apply_command": _execute_command(args, token)}
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            return await InstallationGridRolloutService.apply(
                session, expected_partner_slugs=tuple(args.expected_partner),
                backend_release_commit=args.backend_release_commit,
                backend_image_digest=args.backend_image_digest,
                web_v2_commit=args.web_v2_commit,
                web_v2_proof=args.web_v2_proof,
                manager_editor_proof=args.manager_editor_proof,
                legacy_list_proof=args.legacy_list_proof,
                legacy_calculate_proof=args.legacy_calculate_proof,
                legacy_tariff_calculate_proof=args.legacy_tariff_calculate_proof,
                include_demo_reset=args.include_demo_reset,
                plan_token=args.plan_token,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--expected-partner", action="append", default=[],
                        help="Exact active partner slug; repeat for every discovered partner")
    parser.add_argument("--backend-release-commit", help="Reviewed active backend release SHA")
    parser.add_argument("--backend-image-digest", help="Reviewed immutable backend image digest")
    parser.add_argument("--web-v2-commit", help="Reviewed deployed web v2 commit SHA")
    parser.add_argument("--web-v2-proof", help="URL of web v2 runtime smoke evidence")
    parser.add_argument("--manager-editor-proof", help="URL showing legacy rate editor is guarded")
    parser.add_argument("--legacy-list-proof",
                        help="URL showing installation rates and options/content lists are guarded")
    parser.add_argument("--legacy-calculate-proof", help="URL showing legacy calculator fails closed")
    parser.add_argument("--legacy-tariff-calculate-proof",
                        help="URL showing old installation ServiceTariff calculator fails closed")
    parser.add_argument("--include-demo-reset", action="store_true",
                        help="Explicitly include demo_read_only partners in this operator-only reset")
    parser.add_argument("--plan-token", help="Fresh signed token emitted by a ready plan")
    args = parser.parse_args()
    if (args.action == "apply") != bool(args.plan_token):
        parser.error("Only apply requires a fresh --plan-token")
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        # Never print connection strings, tokens, or full tenant data on error.
        print(f"installation_grid_rollout status=blocked error_type={type(exc).__name__}",
              file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
