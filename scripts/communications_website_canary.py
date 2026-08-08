#!/usr/bin/env python3
"""Plan, arm, inspect, or finalize one exact tenant website canary event."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Literal


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CommandMode = Literal["plan", "arm", "status", "complete"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate one immutable tenant website Telegram canary. The target "
            "is one exact event, tenant, storefront, and eligible recipient key."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--arm", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--complete", action="store_true")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--event-type", required=True)
    parser.add_argument("--tenant-id", required=True, type=int)
    parser.add_argument("--storefront-id", required=True, type=int)
    parser.add_argument("--recipient-key", required=True)
    parser.add_argument(
        "--expected-control-revision",
        type=int,
        help="Required by --arm; use the exact revision returned by --plan",
    )
    return parser


def _mode(args: argparse.Namespace) -> CommandMode:
    if args.plan:
        return "plan"
    if args.arm:
        return "arm"
    if args.status:
        return "status"
    return "complete"


async def run_command(
    mode: CommandMode,
    *,
    run_id: str,
    event_id: str,
    event_type: str,
    tenant_id: int,
    storefront_id: int,
    recipient_key: str,
    expected_control_revision: int | None = None,
    session_factory=None,
    config=None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    from core.config import settings
    from core.database import async_session_maker
    from services.communications.runtime_config import CommunicationRuntimeConfig
    from services.communications.website_canary import (
        TenantWebsiteCommunicationsCanary,
    )
    from services.communications.website_canary_target import WebsiteCanaryTarget

    if mode == "arm" and expected_control_revision is None:
        raise ValueError("--arm requires --expected-control-revision")
    target = WebsiteCanaryTarget(
        event_id=event_id,
        event_type=event_type,
        tenant_id=tenant_id,
        storefront_id=storefront_id,
        recipient_key=recipient_key,
    )
    effective_factory = session_factory or async_session_maker
    effective_config = config or CommunicationRuntimeConfig.from_settings()
    effective_token = settings.BOT_TOKEN if bot_token is None else bot_token
    async with effective_factory() as session:
        try:
            if mode == "plan":
                snapshot = await TenantWebsiteCommunicationsCanary.plan(
                    session,
                    run_id=run_id,
                    target=target,
                    config=effective_config,
                    bot_token=effective_token,
                )
                await session.rollback()
            elif mode == "arm":
                snapshot = await TenantWebsiteCommunicationsCanary.arm(
                    session,
                    run_id=run_id,
                    target=target,
                    expected_control_revision=int(expected_control_revision),
                    config=effective_config,
                    bot_token=effective_token,
                )
                await session.commit()
            elif mode == "status":
                snapshot = await TenantWebsiteCommunicationsCanary.status(
                    session,
                    run_id=run_id,
                    target=target,
                )
                await session.rollback()
            else:
                snapshot = await TenantWebsiteCommunicationsCanary.complete(
                    session,
                    run_id=run_id,
                    target=target,
                )
                await session.commit()
            return snapshot.to_dict()
        except Exception:
            await session.rollback()
            raise


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(
            run_command(
                _mode(args),
                run_id=args.run_id,
                event_id=args.event_id,
                event_type=args.event_type,
                tenant_id=args.tenant_id,
                storefront_id=args.storefront_id,
                recipient_key=args.recipient_key,
                expected_control_revision=args.expected_control_revision,
            )
        )
    except Exception as error:
        from services.communications.website_canary import (
            WebsiteCanaryControlRejected,
        )

        error_code = (
            error.error_code
            if isinstance(error, WebsiteCanaryControlRejected)
            else "website_canary_command_failed"
        )
        _print_json({"ok": False, "error_code": str(error_code)})
        return 1
    _print_json({"ok": True, **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
