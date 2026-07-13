#!/usr/bin/env python3
"""Plan, enqueue, or inspect a bounded Telegram communications canary run."""

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

CanaryMode = Literal["plan", "execute", "status"]


class CanaryCommandRejected(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


def _run_id(value: str) -> str:
    from services.communications.canary_run_id import normalize_canary_run_id

    try:
        return normalize_canary_run_id(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "run id must be a canonical lowercase UUIDv4"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate one idempotent Telegram communications canary run. "
            "No destination or message arguments are accepted."
        )
    )
    parser.add_argument(
        "--run-id",
        required=True,
        type=_run_id,
        help="Canonical lowercase UUIDv4 identifying this immutable run",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="Run safety checks only")
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Enqueue the fixed event; never sends Telegram directly",
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="Show privacy-safe event and delivery status",
    )
    return parser


def _mode(args: argparse.Namespace) -> CanaryMode:
    if args.plan:
        return "plan"
    if args.execute:
        return "execute"
    return "status"


async def run_command(
    mode: CanaryMode,
    *,
    run_id: str,
    session_factory=None,
    app_role: str | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    # Import application configuration only after CLI parsing, so --help is
    # always available without loading credentials or opening infrastructure.
    from services.communications.canary_errors import (
        CommunicationsCanarySafetyError,
    )
    from services.communications.outbox_service import OutboxEventConflictError
    from core.config import settings
    from core.database import async_session_maker
    from services.communications.canary import CommunicationsTelegramCanary

    effective_session_factory = session_factory or async_session_maker
    effective_app_role = settings.APP_ROLE if app_role is None else app_role
    effective_bot_token = settings.BOT_TOKEN if bot_token is None else bot_token

    try:
        normalized_run_id = CommunicationsTelegramCanary.normalize_run_id(run_id)
        async with effective_session_factory() as session:
            try:
                if mode == "status":
                    await CommunicationsTelegramCanary.preflight_runtime(
                        session,
                        app_role=effective_app_role,
                        bot_token=effective_bot_token,
                    )
                    result = await CommunicationsTelegramCanary.status_snapshot(
                        session,
                        run_id=normalized_run_id,
                    )
                    await session.rollback()
                    return result

                preflight = await CommunicationsTelegramCanary.preflight(
                    session,
                    app_role=effective_app_role,
                    bot_token=effective_bot_token,
                )
                if mode == "plan":
                    existing = (
                        await CommunicationsTelegramCanary.assert_existing_snapshot_compatible(
                            session,
                            run_id=normalized_run_id,
                            recipient_keys=preflight.recipient_keys,
                        )
                    )
                    result = CommunicationsTelegramCanary.plan_snapshot(
                        preflight,
                        run_id=normalized_run_id,
                        existing=existing,
                    )
                    await session.rollback()
                    return result

                enqueue_result = await CommunicationsTelegramCanary.enqueue(
                    session,
                    run_id=normalized_run_id,
                    recipient_keys=preflight.recipient_keys,
                )
                result = await CommunicationsTelegramCanary.execute_snapshot(
                    session,
                    preflight,
                    enqueue_result,
                    run_id=normalized_run_id,
                )
                # The CLI owns this transaction. The producer above deliberately
                # cannot commit and never imports or invokes a Telegram provider.
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
    except CommunicationsCanarySafetyError as exc:
        raise CanaryCommandRejected(exc.error_code) from None
    except OutboxEventConflictError:
        raise CanaryCommandRejected("canary_snapshot_conflict") from None


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(run_command(_mode(args), run_id=args.run_id))
    except CanaryCommandRejected as exc:
        _print_json({"ok": False, "error_code": exc.error_code})
        return 2
    except Exception:
        # Do not print exception text: database/provider errors may contain
        # connection details or other operational secrets.
        _print_json({"ok": False, "error_code": "canary_command_failed"})
        return 1

    _print_json({"ok": True, **payload})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
