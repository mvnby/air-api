"""Deprecated Orsha CLI adapter over generic storefront onboarding."""

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

from services.orsha_storefront_bootstrap_service import (  # noqa: E402
    OrshaStorefrontBootstrapBlockedError,
    OrshaStorefrontBootstrapService,
)
from services.orsha_storefront_manifest import (  # noqa: E402
    OrshaStorefrontManifestError,
)
from services.tenant_offer_catalog_invalidation import (  # noqa: E402
    TenantOfferCatalogInvalidationUnavailableError,
)


MAX_MANIFEST_BYTES = 64 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage the bounded internal Orsha storefront. Planning is the default; "
            "every mutation requires the exact token from a fresh plan."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true")
    mode.add_argument(
        "--plan-for",
        choices=("bootstrap", "verify-domain", "activate", "disable"),
        metavar="ACTION",
    )
    mode.add_argument("--execute", action="store_true", help="Execute bootstrap.")
    mode.add_argument("--verify-domain", action="store_true")
    mode.add_argument("--activate", action="store_true")
    mode.add_argument("--disable", action="store_true")
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--plan-token")
    parser.add_argument(
        "--offers-file",
        type=Path,
        help="JSON object with version=1 and an offers array (maximum 64 KiB).",
    )
    parser.add_argument(
        "--offer-slug",
        action="append",
        nargs=4,
        metavar=("SLUG", "PRICE", "OLD_PRICE_OR_DASH", "PUBLISHED"),
    )
    parser.add_argument(
        "--offer-id",
        action="append",
        nargs=4,
        metavar=("ID", "PRICE", "OLD_PRICE_OR_DASH", "PUBLISHED"),
    )
    return parser


def action_and_mode(args: argparse.Namespace) -> tuple[str | None, str]:
    if args.status:
        return None, "status"
    if args.execute:
        return "bootstrap", "execute"
    if args.verify_domain:
        return "verify-domain", "execute"
    if args.activate:
        return "activate", "execute"
    if args.disable:
        return "disable", "execute"
    return args.plan_for or "bootstrap", "plan"


def validate_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    action, mode = action_and_mode(args)
    has_offers = bool(args.offers_file or args.offer_slug or args.offer_id)
    if mode == "execute" and not args.plan_token:
        parser.error("mutations require --plan-token from a fresh plan")
    if mode != "execute" and args.plan_token:
        parser.error("--plan-token is accepted only for mutations")
    if (mode == "status" or action in {"verify-domain", "disable"}) and has_offers:
        parser.error("status, verify-domain and disable do not accept offer inputs")
    if mode != "status" and action in {"bootstrap", "activate"} and not has_offers:
        parser.error("bootstrap and activate require an explicit offer allowlist")


def load_offer_specs(args: argparse.Namespace) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if args.offers_file:
        values.extend(_read_manifest(args.offers_file))
    for raw in args.offer_slug or ():
        values.append(_argument_offer("product_slug", raw))
    for raw in args.offer_id or ():
        values.append(_argument_offer("product_id", raw))
    return values


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise OrshaStorefrontManifestError("offers file cannot be read") from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise OrshaStorefrontManifestError("offers file exceeds 64 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OrshaStorefrontManifestError("offers file is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "offers"}:
        raise OrshaStorefrontManifestError(
            "offers file must contain exactly version and offers"
        )
    if payload["version"] != 1 or isinstance(payload["version"], bool):
        raise OrshaStorefrontManifestError("offers file version must be 1")
    if not isinstance(payload["offers"], list):
        raise OrshaStorefrontManifestError("offers must be an array")
    return payload["offers"]


def _argument_offer(reference_field: str, raw: list[str]) -> dict[str, Any]:
    reference, price, old_price, published = raw
    if published not in {"true", "false"}:
        raise OrshaStorefrontManifestError("PUBLISHED must be true or false")
    return {
        reference_field: reference,
        "price": price,
        "old_price": None if old_price == "-" else old_price,
        "is_published": published == "true",
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from core.database import async_session_maker

    action, mode = action_and_mode(args)
    offer_specs = load_offer_specs(args)
    async with async_session_maker() as session:
        try:
            if mode == "status":
                return await OrshaStorefrontBootstrapService.status(
                    session,
                    hostname=args.hostname,
                )
            if mode == "plan":
                result = await OrshaStorefrontBootstrapService.plan(
                    session,
                    action=str(action),
                    hostname=args.hostname,
                    offer_specs=offer_specs,
                )
                result["reviewed_execute_command"] = _reviewed_command(args, result)
                return result
            result = await OrshaStorefrontBootstrapService.execute(
                session,
                action=str(action),
                hostname=args.hostname,
                plan_token=args.plan_token,
                offer_specs=offer_specs,
            )
            await session.commit()
            return result
        except Exception:
            if mode == "execute":
                await session.rollback()
            raise


def _reviewed_command(args: argparse.Namespace, result: dict[str, Any]) -> str | None:
    if not result["ready"]:
        return None
    action = result["action"]
    command = ["python3", "scripts/manage_orsha_storefront.py"]
    command.append(
        {
            "bootstrap": "--execute",
            "verify-domain": "--verify-domain",
            "activate": "--activate",
            "disable": "--disable",
        }[
            action
        ]
    )
    command.extend(["--hostname", result["hostname"]])
    if args.offers_file:
        command.extend(["--offers-file", str(args.offers_file)])
    for values in args.offer_slug or ():
        command.extend(["--offer-slug", *values])
    for values in args.offer_id or ():
        command.extend(["--offer-id", *values])
    command.extend(["--plan-token", result["plan_token"]])
    return shlex.join(command)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (
        OrshaStorefrontBootstrapBlockedError,
        OrshaStorefrontManifestError,
        TenantOfferCatalogInvalidationUnavailableError,
        ValueError,
    ) as exc:
        print(f"orsha_storefront status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except IntegrityError as exc:
        print(
            "orsha_storefront status=blocked error=database state changed concurrently",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "orsha_storefront status=error error=unexpected transaction failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if result.get("ready") is False or result.get("ownership_safe") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
