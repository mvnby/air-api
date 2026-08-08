#!/usr/bin/env python3
"""Compatibility CLI for the five-type tenant website notification runtime."""

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

CommandMode = Literal["plan", "enable", "status", "off"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate the fixed five-type tenant website Telegram delivery "
            "allowlist. The historical filename is retained for automation "
            "compatibility; event types and destinations are not configurable."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan",
        action="store_true",
        help="Inspect activation gates without changing runtime control",
    )
    mode.add_argument(
        "--enable",
        action="store_true",
        help="Atomically activate the fixed tenant owner/admin delivery scope",
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="Show privacy-safe runtime and outcome counts",
    )
    mode.add_argument(
        "--off",
        action="store_true",
        help="Emergency-disable delivery and wait for in-flight work to drain",
    )
    return parser


def _mode(args: argparse.Namespace) -> CommandMode:
    if args.plan:
        return "plan"
    if args.enable:
        return "enable"
    if args.status:
        return "status"
    return "off"


async def run_command(
    mode: CommandMode,
    *,
    session_factory=None,
    config=None,
    bot_token: str | None = None,
    runtime_locks_enabled: bool | None = None,
    off_wait_seconds: float = 30.0,
) -> dict[str, Any]:
    from core.config import settings
    from core.database import async_session_maker
    from services.communications.installation_notifications import (
        WebsiteNotificationOperations,
    )
    from services.communications.runtime_config import CommunicationRuntimeConfig
    from services.communications.runtime_state import (
        CommunicationRuntimeMode,
        CommunicationRuntimeStateService,
    )

    effective_factory = session_factory or async_session_maker
    if mode == "off":
        async with effective_factory() as session:
            try:
                previous = await CommunicationRuntimeStateService.read_control(
                    session,
                    channel=WebsiteNotificationOperations.CHANNEL,
                )
                control = await CommunicationRuntimeStateService.set_mode(
                    session,
                    channel=WebsiteNotificationOperations.CHANNEL,
                    mode=CommunicationRuntimeMode.OFF,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        drain = await WebsiteNotificationOperations.wait_until_off_drained(
            effective_factory,
            wait_seconds=off_wait_seconds,
        )
        return {
            "command": "off",
            "previous_mode": previous.mode.value,
            "control_revision": control.control_revision,
            "activation_watermark": (
                control.installation_estimate_watermark_at.isoformat()
                if control.installation_estimate_watermark_at is not None
                else None
            ),
            **drain,
        }

    effective_config = config or CommunicationRuntimeConfig.from_settings()
    effective_token = settings.BOT_TOKEN if bot_token is None else bot_token
    effective_locks_enabled = (
        settings.RUNTIME_DB_LOCKS_ENABLED
        if runtime_locks_enabled is None
        else bool(runtime_locks_enabled)
    )

    async with effective_factory() as session:
        try:
            if mode in {"plan", "status"}:
                inspection = await WebsiteNotificationOperations.inspect(
                    session,
                    config=effective_config,
                    bot_token=effective_token,
                    runtime_locks_enabled=effective_locks_enabled,
                )
                await session.rollback()
                return {
                    "command": mode,
                    **inspection.to_dict(),
                }

            inspection, revision, watermark = (
                await WebsiteNotificationOperations.activate_installation_from_off(
                    session,
                    config=effective_config,
                    bot_token=effective_token,
                    runtime_locks_enabled=effective_locks_enabled,
                )
            )
            await session.commit()
            return {
                "command": "enable",
                "profile": inspection.profile,
                "runtime_mode": CommunicationRuntimeMode.ALL.value,
                "control_revision": revision,
                "activation_watermark": watermark.isoformat(),
                "owner_recipient_count": inspection.owner_recipient_count,
                "ambiguous_nonterminal_count": (
                    inspection.ambiguous_nonterminal_count
                ),
                "ambiguous_terminal_count": (
                    inspection.ambiguous_terminal_count
                ),
                "ambiguous_total_count": inspection.ambiguous_total_count,
            }
        except Exception:
            await session.rollback()
            raise


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(run_command(_mode(args)))
    except Exception as error:
        from services.communications.installation_notifications import (
            InstallationNotificationControlRejected,
        )

        error_code = (
            error.error_code
            if isinstance(error, InstallationNotificationControlRejected)
            else "installation_notification_command_failed"
        )
        # Never print exception text: provider/database details can contain
        # secrets, destinations, or customer data.
        _print_json({"ok": False, "error_code": str(error_code)})
        return 2 if isinstance(error, InstallationNotificationControlRejected) else 1

    if result.get("command") == "off" and not result.get("drained", False):
        _print_json(
            {
                "ok": False,
                "error_code": "installation_notification_drain_incomplete",
                **result,
            }
        )
        return 3
    _print_json({"ok": True, **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
