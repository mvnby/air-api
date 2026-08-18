"""Plan and execute a reviewed, system-owned shared catalog projection."""

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

from services.shared_catalog_grant_manifest import (  # noqa: E402
    SharedCatalogGrantManifest,
    SharedCatalogGrantManifestError,
)
from services.shared_catalog_grant_planner import (  # noqa: E402
    SharedCatalogGrantBlockedError,
)
from services.shared_catalog_grant_service import (  # noqa: E402
    SharedCatalogGrantService,
)
from services.tenant_offer_catalog_invalidation import (  # noqa: E402
    TenantOfferCatalogInvalidationUnavailableError,
)


MAX_MANIFEST_BYTES = 16 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review or execute one bounded shared-catalog projection batch. "
            "Execution requires the exact unexpired token from a fresh plan."
        )
    )
    parser.add_argument("action", choices=("plan", "execute"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--desired-status",
        choices=("active", "disabled"),
        required=True,
    )
    parser.add_argument("--plan-token")
    return parser


def validate_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if args.action == "plan" and args.plan_token:
        parser.error("plan does not accept --plan-token")
    if args.action == "execute" and not args.plan_token:
        parser.error("execute requires --plan-token from a fresh plan")


def read_manifest(path: Path) -> SharedCatalogGrantManifest:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise SharedCatalogGrantManifestError(
            "Grant manifest file cannot be read"
        ) from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise SharedCatalogGrantManifestError("Grant manifest exceeds 16 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SharedCatalogGrantManifestError(
            "Grant manifest is not valid UTF-8 JSON"
        ) from exc
    return SharedCatalogGrantManifest.normalize(payload)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from core.database import async_session_maker

    manifest = read_manifest(args.manifest)
    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                result = await SharedCatalogGrantService.plan(
                    session,
                    desired_status=args.desired_status,
                    manifest=manifest,
                )
                result["reviewed_execute_command"] = reviewed_command(args, result)
                return result
            result = await SharedCatalogGrantService.execute(
                session,
                desired_status=args.desired_status,
                manifest=manifest,
                plan_token=args.plan_token,
            )
            await session.commit()
            return result
        except Exception:
            if args.action == "execute":
                await session.rollback()
            raise


def reviewed_command(
    args: argparse.Namespace,
    result: dict[str, Any],
) -> str | None:
    if not result["ready"]:
        return None
    return shlex.join(
        [
            "python3",
            "scripts/manage_shared_catalog_grant.py",
            "execute",
            "--manifest",
            str(args.manifest),
            "--desired-status",
            result["desired_status"],
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
        SharedCatalogGrantBlockedError,
        SharedCatalogGrantManifestError,
        TenantOfferCatalogInvalidationUnavailableError,
        ValueError,
    ) as exc:
        print(f"shared_catalog_grant status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except IntegrityError as exc:
        print(
            "shared_catalog_grant status=blocked "
            "error=database state changed concurrently",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "shared_catalog_grant status=error "
            "error=unexpected transaction failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if result.get("ready") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
