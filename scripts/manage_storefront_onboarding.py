"""Safely plan and execute a bounded tenant/storefront onboarding manifest."""

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

from services.storefront_onboarding_manifest import (  # noqa: E402
    StorefrontOnboardingManifest,
    StorefrontOnboardingManifestError,
)
from services.storefront_onboarding_service import (  # noqa: E402
    StorefrontOnboardingBlockedError,
    StorefrontOnboardingService,
)
from services.tenant_offer_catalog_invalidation import (  # noqa: E402
    TenantOfferCatalogInvalidationUnavailableError,
)


MAX_MANIFEST_BYTES = 64 * 1024
LIFECYCLE_ACTIONS = ("bootstrap", "verify-domain", "activate", "disable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage one closed storefront onboarding manifest. Planning is "
            "read-only; every lifecycle mutation requires the exact, unexpired "
            "token from a fresh plan."
        )
    )
    parser.add_argument(
        "action", choices=("plan", *LIFECYCLE_ACTIONS), help="Lifecycle command"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument(
        "--for-action",
        choices=LIFECYCLE_ACTIONS,
        help="Lifecycle action to review when action=plan",
    )
    parser.add_argument("--plan-token")
    return parser


def validate_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if args.action == "plan":
        if not args.for_action:
            parser.error("plan requires --for-action")
        if args.plan_token:
            parser.error("plan does not accept --plan-token")
        return
    if args.for_action:
        parser.error("--for-action is accepted only by plan")
    if not args.plan_token:
        parser.error("lifecycle mutations require --plan-token from a fresh plan")


def read_manifest(path: Path) -> StorefrontOnboardingManifest:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise StorefrontOnboardingManifestError(
            "Manifest file cannot be read"
        ) from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise StorefrontOnboardingManifestError("Manifest exceeds 64 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StorefrontOnboardingManifestError(
            "Manifest is not valid UTF-8 JSON"
        ) from exc
    return StorefrontOnboardingManifest.normalize(payload)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from core.database import async_session_maker

    manifest = read_manifest(args.manifest)
    lifecycle_action = args.for_action if args.action == "plan" else args.action
    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                result = await StorefrontOnboardingService.plan(
                    session,
                    action=str(lifecycle_action),
                    hostname=args.hostname,
                    manifest=manifest,
                )
                result["reviewed_execute_command"] = reviewed_command(
                    args, result
                )
                return result
            result = await StorefrontOnboardingService.execute(
                session,
                action=str(lifecycle_action),
                hostname=args.hostname,
                manifest=manifest,
                plan_token=args.plan_token,
            )
            await session.commit()
            return result
        except Exception:
            if args.action != "plan":
                await session.rollback()
            raise


def reviewed_command(
    args: argparse.Namespace,
    result: dict[str, Any],
) -> str | None:
    if not result["ready"]:
        return None
    command = [
        "python3",
        "scripts/manage_storefront_onboarding.py",
        result["action"],
        "--manifest",
        str(args.manifest),
        "--hostname",
        result["hostname"],
        "--plan-token",
        result["plan_token"],
    ]
    return shlex.join(command)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (
        StorefrontOnboardingBlockedError,
        StorefrontOnboardingManifestError,
        TenantOfferCatalogInvalidationUnavailableError,
        ValueError,
    ) as exc:
        print(f"storefront_onboarding status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except IntegrityError as exc:
        print(
            "storefront_onboarding status=blocked "
            "error=database state changed concurrently",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "storefront_onboarding status=error "
            "error=unexpected transaction failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if result.get("ready") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
