"""Backfill legacy Product.images files into product media storage.

Default mode is dry-run. Use --execute only after reviewing planned uploads.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(".")

from services.media_storage_service import get_product_media_storage  # noqa: E402
from services.product_legacy_images_backfill_service import (  # noqa: E402
    ProductLegacyImagesBackfillService,
)


STORAGE_PROVIDERS = ("local", "r2", "s3", "s3_compatible")


async def backfill_product_legacy_images_storage(
    *,
    session: AsyncSession,
    execute: bool,
    provider: str | None,
    limit: int,
    product_id: int | None,
    after_product_id: int | None,
    published_only: bool,
    force: bool,
) -> dict[str, Any]:
    storage = get_product_media_storage(provider, require_write=execute)
    return await ProductLegacyImagesBackfillService.backfill_to_storage(
        session=session,
        storage=storage,
        execute=execute,
        limit=limit,
        product_id=product_id,
        after_product_id=after_product_id,
        published_only=published_only,
        force=force,
    )


async def run(
    *,
    execute: bool,
    provider: str | None,
    limit: int,
    product_id: int | None,
    after_product_id: int | None,
    published_only: bool,
    force: bool,
) -> dict[str, Any]:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        return await backfill_product_legacy_images_storage(
            session=session,
            execute=execute,
            provider=provider,
            limit=limit,
            product_id=product_id,
            after_product_id=after_product_id,
            published_only=published_only,
            force=force,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute upload of legacy Product.images local files "
            "to the configured product media storage provider."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Upload files and create/update ProductImage original variants.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force report-only mode. This is already the default.",
    )
    parser.add_argument(
        "--provider",
        choices=STORAGE_PROVIDERS,
        default=None,
        help="Storage provider override. Defaults to PRODUCT_MEDIA_STORAGE_PROVIDER.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum products to inspect in this run (1-1000, default: 50).",
    )
    parser.add_argument(
        "--product-id",
        type=int,
        default=None,
        help="Limit backfill plan to one product id.",
    )
    parser.add_argument(
        "--after-product-id",
        type=int,
        default=None,
        help="Only inspect products with id greater than this value.",
    )
    parser.add_argument(
        "--published-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only inspect published products by default.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-upload even if the exact ProductImage original is already on target storage.",
    )
    return parser


def print_report(report: dict[str, Any]) -> None:
    print("Product Legacy Images Storage Backfill")
    print(f"  mode={'DRY-RUN' if report['dry_run'] else 'EXECUTE'}")
    print(f"  storage_provider={report['storage_provider']}")
    print(f"  product_id={report['product_id'] or 'all'}")
    print(f"  limit={report['limit']}")
    print(f"  after_product_id={report['after_product_id'] or 'none'}")
    print(f"  published_only={report['published_only']}")
    print(f"  force={report['force']}")
    print(f"  inspected_products={report['inspected']}")
    print(f"  inspected_images={report['inspected_images']}")
    print(f"  planned_uploads={report['planned_uploads']}")
    print(f"  skipped={report['skipped_count']}")
    if not report["dry_run"]:
        print(f"  uploaded={report['uploaded']}")
        print(f"  updated_variants={report['updated_variants']}")
        print(f"  errors={len(report['errors'])}")

    if report["items"]:
        print("\nPlanned uploads" if report["dry_run"] else "\nUploaded")
        rows = report["items"] if report["dry_run"] else report.get("uploaded_items", [])
        for item in rows[:50]:
            create_marker = " create-image" if item.get("will_create_product_image") else ""
            print(
                "  - "
                f"product#{item['product_id']} image={item['image_url']} "
                f"target={item['target_url']}{create_marker}"
            )
        if len(rows) > 50:
            print(f"  ... {len(rows) - 50} more")

    if report["skipped"]:
        print("\nSkipped")
        for item in report["skipped"][:30]:
            print(
                "  - "
                f"product#{item['product_id']} reason={item.get('skip_reason')} "
                f"image={item.get('image_url')}"
            )
        if len(report["skipped"]) > 30:
            print(f"  ... {len(report['skipped']) - 30} more")

    if report["errors"]:
        print("\nErrors")
        for item in report["errors"]:
            print(
                "  - "
                f"product#{item['product_id']} image={item['image_url']} "
                f"error={item['error']}"
            )

    if report["dry_run"]:
        print("\nDry run only. Use --execute after reviewing this bounded plan.")


def main() -> None:
    args = build_parser().parse_args()
    report = asyncio.run(
        run(
            execute=bool(args.execute and not args.dry_run),
            provider=args.provider,
            limit=args.limit,
            product_id=args.product_id,
            after_product_id=args.after_product_id,
            published_only=args.published_only,
            force=args.force,
        )
    )
    print_report(report)


if __name__ == "__main__":
    main()
