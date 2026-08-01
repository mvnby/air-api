#!/usr/bin/env python3
"""Inspect or terminally suppress an explicit five-event website manifest."""

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


def _expected_count(value: str) -> int:
    from services.communications.backlog_reconciliation_contracts import (
        MAX_RECONCILIATION_LIMIT,
    )

    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected-count must be an integer"
        ) from None
    if not 0 <= parsed <= MAX_RECONCILIATION_LIMIT:
        raise argparse.ArgumentTypeError(
            f"expected-count must be between 0 and {MAX_RECONCILIATION_LIMIT}"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile the reviewed five-type tenant website notification "
            "backlog. Repeat each manifest flag once per event type. "
            "Execution is terminal no-send only and commits all five types "
            "atomically."
        )
    )
    parser.add_argument(
        "--event-type",
        required=True,
        action="append",
        help="Allowlisted event type; repeat once per manifest entry",
    )
    parser.add_argument(
        "--cutoff",
        required=True,
        action="append",
        type=_cutoff,
        help="Exclusive created_at cutoff paired by position",
    )
    parser.add_argument(
        "--expected-count",
        required=True,
        action="append",
        type=_expected_count,
        help="Exact candidate count paired by position",
    )
    parser.add_argument(
        "--disposition",
        required=True,
        action="append",
        choices=("retain", "terminal_no_send"),
        help="retain or terminal_no_send, paired by position",
    )
    parser.add_argument(
        "--operation-id",
        required=True,
        help="Unique UUID recorded in terminal no-send audit messages",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist the exact five-entry manifest; omitted means dry-run",
    )
    return parser


def _manifest(args: argparse.Namespace):
    from services.communications.website_backlog_reconciliation import (
        WebsiteBacklogManifestItem,
    )

    lengths = {
        len(args.event_type),
        len(args.cutoff),
        len(args.expected_count),
        len(args.disposition),
    }
    if len(lengths) != 1:
        raise ValueError("Website backlog manifest flag counts must match")
    return tuple(
        WebsiteBacklogManifestItem(
            event_type=event_type,
            cutoff=cutoff,
            expected_count=expected_count,
            disposition=disposition,
        )
        for event_type, cutoff, expected_count, disposition in zip(
            args.event_type,
            args.cutoff,
            args.expected_count,
            args.disposition,
            strict=True,
        )
    )


async def run_command(
    *,
    manifest,
    operation_id: str,
    execute: bool = False,
    now: datetime | None = None,
    session_factory=None,
) -> dict[str, Any]:
    from core.config import settings
    from core.database import async_session_maker
    from services.communications.backlog_reconciliation import (
        InstallationEstimateBacklogExecutionBlocked,
    )
    from services.communications.runtime_config import CommunicationRuntimeConfig
    from services.communications.website_backlog_reconciliation import (
        WebsiteCommunicationBacklogReconciliation,
    )
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
                report = await WebsiteCommunicationBacklogReconciliation.reconcile_manifest(
                    session,
                    manifest=tuple(manifest),
                    operation_id=operation_id,
                    execute=execute,
                    now=now,
                    runtime_lock=runtime_lock,
                    app_role=settings.APP_ROLE,
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
        result = asyncio.run(
            run_command(
                manifest=_manifest(args),
                operation_id=args.operation_id,
                execute=bool(args.execute),
            )
        )
    except Exception as error:
        from services.communications.backlog_reconciliation import (
            InstallationEstimateBacklogExecutionBlocked,
        )

        error_code = (
            error.error_code
            if isinstance(error, InstallationEstimateBacklogExecutionBlocked)
            else "website_backlog_command_failed"
        )
        _print_json({"ok": False, "error_code": str(error_code)})
        return 1
    _print_json({"ok": True, **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
