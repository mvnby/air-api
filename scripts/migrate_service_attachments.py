#!/usr/bin/env python3
"""Backfill private service attachments and equipment links from legacy data.

The default mode is a read-only dry run. Use ``--execute`` only after reviewing
the report. Legacy JSON fields are deliberately left untouched so the migration
can be audited and repeated safely.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep these re-exports stable for operators and existing tests.
from core.config import settings  # noqa: E402, F401
from scripts.service_attachment_migration.attachment_copy import (  # noqa: E402
    _is_existing_attachment,
    migrate_attachments,
)
from scripts.service_attachment_migration.equipment_backfill import (  # noqa: E402
    migrate_equipment_links,
    migrate_legacy_coverages,
)
from scripts.service_attachment_migration.legacy_sources import (  # noqa: E402
    AttachmentDownloadError,
    LegacyAttachmentCandidate,
    MigrationStats,
    _telegram_file_url,
    _validate_legacy_source_url,
    download_candidate,
    extract_order_candidates,
    extract_stage_candidates,
)
from scripts.service_attachment_migration.orchestrator import print_report, run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Persist the migration. Default is dry-run.")
    parser.add_argument("--order-id", type=int, help="Limit the migration to one order.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Persist recoverable rows even when permanent legacy gaps remain. Use only after reviewing dry-run.",
    )
    args = parser.parse_args()
    if args.allow_partial and not args.execute:
        parser.error("--allow-partial can only be used together with --execute")
    try:
        stats = asyncio.run(
            run(
                execute=bool(args.execute),
                order_id=args.order_id,
                allow_partial=bool(args.allow_partial),
            )
        )
    except RuntimeError as exc:
        parser.error(str(exc))
    print_report(stats, execute=bool(args.execute))
    if not args.execute and (
        stats.attachments_unavailable
        or stats.equipment_link_conflicts
        or stats.transient_failures
        or stats.configuration_failures
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
