#!/usr/bin/env python3
"""Legacy installation-only entrypoint kept for compatibility.

Use ``reconcile_website_communication_backlog.py`` for the required five-event
manifest before activating the tenant website notification runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _cutoff(value: str) -> datetime:
    normalized = str(value or "").strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "cutoff must be an ISO-8601 timestamp with timezone"
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "cutoff must be an ISO-8601 timestamp with timezone"
        )
    return parsed.astimezone(timezone.utc)


def _limit(value: str) -> int:
    from services.communications.backlog_reconciliation import (
        MAX_RECONCILIATION_LIMIT,
    )

    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be an integer") from None
    if parsed < 1 or parsed > MAX_RECONCILIATION_LIMIT:
        raise argparse.ArgumentTypeError(
            f"limit must be between 1 and {MAX_RECONCILIATION_LIMIT}"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect stale crm.installation_estimate_lead.created events. "
            "Dry-run is the default; --execute terminally suppresses safe "
            "pending and materialized candidates and never sends a message."
        )
    )
    parser.add_argument(
        "--cutoff",
        required=True,
        type=_cutoff,
        help="Exclusive ISO-8601 created_at cutoff with timezone",
    )
    parser.add_argument(
        "--limit",
        required=True,
        type=_limit,
        help="Maximum number of oldest candidates to inspect or suppress",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist terminal suppression; omitted means privacy-safe dry-run",
    )
    return parser


async def run_command(
    *,
    cutoff: datetime,
    limit: int,
    execute: bool = False,
    now: datetime | None = None,
    session_factory=None,
) -> dict[str, Any]:
    from core.config import settings
    from core.database import async_session_maker
    from services.communications.backlog_reconciliation import (
        InstallationEstimateBacklogExecutionBlocked,
        InstallationEstimateBacklogReconciliation,
    )
    from services.communications.runtime_config import CommunicationRuntimeConfig
    from services.runtime_lock_service import RuntimeLockService

    effective_session_factory = session_factory or async_session_maker
    runtime_lock = None
    if execute:
        config = CommunicationRuntimeConfig.from_settings()
        runtime_lock = await RuntimeLockService.try_acquire(
            effective_session_factory,
            config.lock_name,
            required=True,
        )
        if not runtime_lock.acquired or runtime_lock.connection is None:
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_lock_unavailable"
            )
    try:
        async with effective_session_factory() as session:
            try:
                report = (
                    await InstallationEstimateBacklogReconciliation.reconcile(
                        session,
                        cutoff=cutoff,
                        limit=limit,
                        execute=execute,
                        now=now,
                        runtime_lock=runtime_lock,
                        app_role=settings.APP_ROLE,
                    )
                )
                if execute:
                    if runtime_lock is None or not await runtime_lock.is_held():
                        raise InstallationEstimateBacklogExecutionBlocked(
                            "communications_runtime_lock_lost"
                        )
                    await session.commit()
                else:
                    await session.rollback()
                return report.to_dict()
            except Exception:
                await session.rollback()
                raise
    finally:
        if runtime_lock is not None:
            await runtime_lock.release()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = asyncio.run(
            run_command(
                cutoff=args.cutoff,
                limit=args.limit,
                execute=bool(args.execute),
            )
        )
    except Exception as error:
        # Exception text can contain database connection details.  Keep the
        # operational output restricted to fixed machine-readable error codes.
        from services.communications.backlog_reconciliation import (
            InstallationEstimateBacklogExecutionBlocked,
        )

        safe_error_code = (
            error.error_code
            if isinstance(error, InstallationEstimateBacklogExecutionBlocked)
            else "installation_estimate_backlog_command_failed"
        )
        _print_json(
            {
                "ok": False,
                "error_code": str(safe_error_code),
            }
        )
        return 1

    _print_json({"ok": True, **report})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
