"""Plan or execute the reviewed six-brand logo CDN migration."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys

import httpx

sys.path.append(".")

from services.brand_logo_cdn_backfill_service import (  # noqa: E402
    BrandLogoBackfillBlockedError,
    BrandLogoCdnBackfillService,
)
from services.catalog_media_policy import CatalogMediaKind, CatalogMediaPolicy  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the exact reviewed migration of legacy brand logos to the media CDN."
    )
    parser.add_argument(
        "action", nargs="?", choices=("plan", "execute"), default="plan"
    )
    parser.add_argument("--plan-token")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.action == "execute" and not args.plan_token:
        parser.error("execute requires --plan-token from a fresh ready plan")
    if args.action != "execute" and args.plan_token:
        parser.error("--plan-token is accepted only by execute")


async def verify_public() -> dict[str, object]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("https://api.mvn.by/api/v1/content/brands")
        response.raise_for_status()
        rows = response.json()
    blocked = [
        {"id": row.get("id"), "slug": row.get("slug"), "logo_url": row.get("logo_url")}
        for row in rows
        if row.get("logo_url")
        and not CatalogMediaPolicy.is_allowed_cdn(
            row["logo_url"], kind=CatalogMediaKind.CONTENT
        )
    ]
    return {"verified": not blocked, "brand_count": len(rows), "non_cdn_logos": blocked}


async def run(args: argparse.Namespace) -> dict[str, object]:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                result = await BrandLogoCdnBackfillService.plan(session)
                token = result.get("plan_token")
                result["reviewed_execute_command"] = (
                    shlex.join(
                        [
                            "python3",
                            "scripts/manage_brand_logo_cdn_backfill.py",
                            "execute",
                            "--plan-token",
                            str(token),
                        ]
                    )
                    if result.get("ready") and not result.get("complete") and token
                    else None
                )
                await session.rollback()
                return result
            result = await BrandLogoCdnBackfillService.execute(
                session,
                plan_token=args.plan_token,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    verification: dict[str, object] = {"verified": False, "error": "not_run"}
    for attempt in range(1, 6):
        try:
            verification = await verify_public()
        except Exception:
            verification = {"verified": False, "error": "public_verification_failed"}
        verification["attempt"] = attempt
        if verification.get("verified"):
            break
        if attempt < 5:
            await asyncio.sleep(2)
    result["post_commit_public_verification"] = verification
    result["operation_complete"] = bool(verification.get("verified"))
    return result


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (BrandLogoBackfillBlockedError, ValueError) as exc:
        print(f"brand_logo_cdn_backfill status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "brand_logo_cdn_backfill status=error error=unexpected operation failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if args.action == "plan" and not result.get("ready"):
        raise SystemExit(2)
    if args.action == "execute" and not result.get("operation_complete"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
