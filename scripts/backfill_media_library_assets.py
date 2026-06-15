"""Index existing media references into MediaAsset without rewriting URLs.

Default mode is dry-run. Use --execute for bounded writes only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(".")

from services.media_library_service import MediaLibraryService  # noqa: E402


async def backfill_media_library_assets(
    *,
    session: AsyncSession,
    execute: bool,
    limit: int,
    include_remote: bool,
    created_by: str | None,
) -> dict[str, Any]:
    return await MediaLibraryService.backfill_referenced_assets(
        session=session,
        execute=execute,
        limit=limit,
        include_remote=include_remote,
        created_by=created_by,
    )


async def run(
    *,
    execute: bool,
    limit: int,
    include_remote: bool,
    created_by: str | None,
) -> dict[str, Any]:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        return await backfill_media_library_assets(
            session=session,
            execute=execute,
            limit=limit,
            include_remote=include_remote,
            created_by=created_by,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Register existing product/article/brand/service media references in the "
            "manager media library. The command preserves every existing URL."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist MediaAsset rows. Without this flag the command only prints a plan.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode. This is already the default.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum missing URLs to plan/create in this run (1-5000, default: 500).",
    )
    parser.add_argument(
        "--include-remote",
        action="store_true",
        help="Also index http/https references as remote metadata without downloading them.",
    )
    parser.add_argument(
        "--created-by",
        default="media-backfill",
        help="created_by marker for new MediaAsset rows.",
    )
    return parser


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run cannot be used together")
    if args.limit < 1 or args.limit > 5000:
        parser.error("--limit must be between 1 and 5000")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _validate_args(args, parser)

    result = asyncio.run(
        run(
            execute=args.execute and not args.dry_run,
            limit=args.limit,
            include_remote=args.include_remote,
            created_by=args.created_by,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
