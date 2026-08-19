"""Audit, plan, or execute one reviewed product-media URL repair manifest.

Plan is the default. Execute requires the exact unexpired token emitted by a
fresh ready plan. The command never deletes media or changes supplier/pricing
data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

sys.path.append(".")

from services.product_media_url_backfill_download import (  # noqa: E402
    ProductMediaDownloadBlockedError,
)
from services.product_media_url_backfill_manifest import (  # noqa: E402
    ProductMediaUrlBackfillManifest,
    ProductMediaUrlBackfillManifestError,
)
from services.product_media_url_backfill_plan_token import (  # noqa: E402
    ProductMediaUrlBackfillBlockedError,
)
from services.product_media_url_public_audit import (  # noqa: E402
    ProductMediaUrlPublicAudit,
    ProductMediaUrlPublicAuditError,
)


MAX_MANIFEST_BYTES = 64 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit/plan or exact-token execution for a bounded "
            "product-media URL backfill. Plan is the default."
        )
    )
    parser.add_argument("action", nargs="?", choices=("audit", "plan", "execute"), default="plan")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--plan-token")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.action == "execute" and not args.plan_token:
        parser.error("execute requires --plan-token from a fresh ready plan")
    if args.action != "execute" and args.plan_token:
        parser.error("--plan-token is accepted only by execute")


def read_manifest(path: Path) -> ProductMediaUrlBackfillManifest:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise ProductMediaUrlBackfillManifestError(
            "Media backfill manifest cannot be read"
        ) from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ProductMediaUrlBackfillManifestError(
            "Media backfill manifest exceeds 64 KiB"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProductMediaUrlBackfillManifestError(
            "Media backfill manifest is not valid UTF-8 JSON"
        ) from exc
    return ProductMediaUrlBackfillManifest.normalize(payload)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_manifest(args.manifest)
    if args.action == "audit":
        return await ProductMediaUrlPublicAudit.run_reviewed(manifest)

    from core.database import async_session_maker
    from services.product_media_url_backfill_service import (
        ProductMediaUrlBackfillService,
    )

    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                result = await ProductMediaUrlBackfillService.plan(
                    session,
                    manifest=manifest,
                )
                result["reviewed_execute_command"] = reviewed_command(args, result)
                await session.rollback()
                return result
            result = await ProductMediaUrlBackfillService.execute(
                session,
                manifest=manifest,
                plan_token=args.plan_token,
            )
            await session.commit()
            verification = None
            for attempt in range(1, 6):
                try:
                    verification = (
                        await ProductMediaUrlBackfillService.verify_public_residual(
                            manifest
                        )
                    )
                except Exception:
                    verification = {
                        "verified": False,
                        "error": "post_commit_public_verification_failed",
                    }
                verification["attempt"] = attempt
                if verification["verified"]:
                    break
                if attempt < 5:
                    await asyncio.sleep(2)
            result["post_commit_public_verification"] = verification
            result["operation_complete"] = bool(
                verification and verification["verified"]
            )
            return result
        except Exception:
            await session.rollback()
            raise


def reviewed_command(args: argparse.Namespace, result: dict[str, Any]) -> str | None:
    if not result.get("ready") or result.get("complete") or not result.get("plan_token"):
        return None
    return shlex.join(
        [
            "python3",
            "scripts/manage_product_media_url_backfill.py",
            "execute",
            "--manifest",
            str(args.manifest),
            "--plan-token",
            result["plan_token"],
        ]
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (
        IntegrityError,
        ProductMediaDownloadBlockedError,
        ProductMediaUrlBackfillBlockedError,
        ProductMediaUrlBackfillManifestError,
        ProductMediaUrlPublicAuditError,
        ValueError,
    ) as exc:
        print(f"product_media_url_backfill status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "product_media_url_backfill status=error "
            "error=unexpected operation failure",
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
