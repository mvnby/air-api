"""Prepare cached JPEG product images for the Yandex Business feed.

Dry-run is the default. Execute bounded batches repeatedly with the returned
`next_after_product_id` cursor until `inspected` becomes zero.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.append(".")

from services.yandex_feed_image_service import YandexFeedImageService  # noqa: E402


async def run(args: argparse.Namespace) -> dict:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        return await YandexFeedImageService.backfill(
            session,
            execute=args.execute,
            limit=args.limit,
            product_id=args.product_id,
            after_product_id=args.after_product_id,
            force=args.force,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare deterministic 800x800 JPEG variants for published Yandex feed products. "
            "Dry-run is the default."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Persist variants.")
    parser.add_argument("--limit", type=int, default=100, help="Batch size, 1-1000.")
    parser.add_argument("--product-id", type=int, default=None)
    parser.add_argument("--after-product-id", type=int, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even an up-to-date variant.",
    )
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit must be between 1 and 1000")
    if args.product_id is not None and args.product_id < 1:
        parser.error("--product-id must be positive")
    if args.after_product_id is not None and args.after_product_id < 0:
        parser.error("--after-product-id cannot be negative")


def print_result(result: dict) -> None:
    print("Yandex Feed Image Backfill")
    print(f"  mode={'DRY-RUN' if result['dry_run'] else 'EXECUTE'}")
    print(f"  inspected={result['inspected']}")
    print(f"  planned={result['planned']}")
    print(f"  up_to_date={result['up_to_date']}")
    print(f"  missing_sources={len(result['missing_sources'])}")
    print(f"  processed={result['processed']}")
    print(f"  errors={len(result['errors'])}")
    print(f"  next_after_product_id={result['next_after_product_id']}")
    for item in result["items"]:
        print(
            f"  - product#{item['product_id']} reason={item['reason']} "
            f"source={item['source_url']}"
        )
    for item in result["errors"]:
        print(
            f"  ! product#{item['product_id']} error={item['error']}"
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    result = asyncio.run(run(args))
    print_result(result)


if __name__ == "__main__":
    main()
