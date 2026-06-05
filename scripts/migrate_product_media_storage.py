"""Migrate product image originals and variants to configured media storage.

Default mode is dry-run. Use --execute only after reviewing the planned uploads.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(".")

from services.media_storage_service import get_product_media_storage  # noqa: E402
from services.product_image_processing_contract import ProductImageVariantType  # noqa: E402
from services.product_media_migration_service import (  # noqa: E402
    DEFAULT_MIGRATION_VARIANT_TYPES,
    ProductMediaMigrationService,
)


STORAGE_PROVIDERS = ("local", "r2", "s3", "s3_compatible")
MIGRATION_VARIANTS = tuple(
    variant.value
    for variant in (
        ProductImageVariantType.PROCESSED,
        ProductImageVariantType.CARD,
        ProductImageVariantType.FULL,
    )
)


async def migrate_product_media_storage(
    *,
    session: AsyncSession,
    execute: bool,
    provider: str | None,
    limit: int,
    product_id: int | None,
    after_image_id: int | None,
    from_image_id: int | None,
    to_image_id: int | None,
    include_originals: bool,
    include_variants: bool,
    variant_types: list[str] | None,
    include_non_ready: bool,
    force: bool,
) -> dict[str, Any]:
    storage = get_product_media_storage(provider, require_write=execute)
    return await ProductMediaMigrationService.migrate_to_storage(
        session=session,
        storage=storage,
        execute=execute,
        limit=limit,
        product_id=product_id,
        after_image_id=after_image_id,
        from_image_id=from_image_id,
        to_image_id=to_image_id,
        include_originals=include_originals,
        include_variants=include_variants,
        variant_types=variant_types or list(DEFAULT_MIGRATION_VARIANT_TYPES),
        include_non_ready=include_non_ready,
        force=force,
    )


async def run(
    *,
    execute: bool,
    provider: str | None,
    limit: int,
    product_id: int | None,
    after_image_id: int | None,
    from_image_id: int | None,
    to_image_id: int | None,
    include_originals: bool,
    include_variants: bool,
    variant_types: list[str] | None,
    include_non_ready: bool,
    force: bool,
) -> dict[str, Any]:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        return await migrate_product_media_storage(
            session=session,
            execute=execute,
            provider=provider,
            limit=limit,
            product_id=product_id,
            after_image_id=after_image_id,
            from_image_id=from_image_id,
            to_image_id=to_image_id,
            include_originals=include_originals,
            include_variants=include_variants,
            variant_types=variant_types,
            include_non_ready=include_non_ready,
            force=force,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute upload of local product image originals and ready "
            "variants to the configured media storage provider."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Upload files and update ProductImageVariant rows. Default is report-only.",
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
        help=(
            "Storage provider override. Defaults to PRODUCT_MEDIA_STORAGE_PROVIDER. "
            "Use r2 for Cloudflare R2."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum source records to inspect in this run (1-1000, default: 50).",
    )
    parser.add_argument(
        "--product-id",
        type=int,
        default=None,
        help="Limit migration plan to one product id.",
    )
    parser.add_argument(
        "--after-image-id",
        type=int,
        default=None,
        help=(
            "Only inspect ProductImage rows with id greater than this value. "
            "Use to continue after a previous bounded batch."
        ),
    )
    parser.add_argument(
        "--from-image-id",
        type=int,
        default=None,
        help="Only inspect ProductImage rows with id greater than or equal to this value.",
    )
    parser.add_argument(
        "--to-image-id",
        type=int,
        default=None,
        help="Only inspect ProductImage rows with id less than or equal to this value.",
    )
    parser.add_argument(
        "--include-originals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Plan ProductImage original files into original variant rows.",
    )
    parser.add_argument(
        "--include-variants",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Plan existing ready ProductImageVariant rows.",
    )
    parser.add_argument(
        "--variant-type",
        action="append",
        choices=MIGRATION_VARIANTS,
        default=None,
        help=(
            "Variant type to include. Repeat for multiple values. "
            "Defaults to processed, card, and full."
        ),
    )
    parser.add_argument(
        "--include-non-ready",
        action="store_true",
        help="Also include non-ready variant rows that still point to local files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-plan rows already marked with the target storage provider.",
    )
    return parser


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run cannot be used together")
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit must be between 1 and 1000")
    if args.product_id is not None and args.product_id < 1:
        parser.error("--product-id must be a positive integer")
    for attr in ("after_image_id", "from_image_id", "to_image_id"):
        value = getattr(args, attr)
        if value is not None and value < 1:
            parser.error(f"--{attr.replace('_', '-')} must be a positive integer")
    if args.after_image_id is not None and args.from_image_id is not None:
        parser.error("Use either --after-image-id or --from-image-id, not both")
    if (
        args.from_image_id is not None
        and args.to_image_id is not None
        and args.from_image_id > args.to_image_id
    ):
        parser.error("--from-image-id must be less than or equal to --to-image-id")
    if (
        args.after_image_id is not None
        and args.to_image_id is not None
        and args.after_image_id >= args.to_image_id
    ):
        parser.error("--after-image-id must be less than --to-image-id")
    if not args.include_originals and not args.include_variants:
        parser.error("At least one of --include-originals or --include-variants is required")


def _print_result(result: dict[str, Any]) -> None:
    mode = "DRY-RUN" if result["dry_run"] else "EXECUTE"
    print("Product Media Storage Migration")
    print(f"  mode={mode}")
    print(f"  storage_provider={result['storage_provider']}")
    print(f"  product_id={result.get('product_id') or 'all'}")
    print(f"  limit={result['limit']}")
    print(f"  after_image_id={result.get('after_image_id') or 'none'}")
    print(f"  from_image_id={result.get('from_image_id') or 'none'}")
    print(f"  to_image_id={result.get('to_image_id') or 'none'}")
    print(f"  include_originals={result['include_originals']}")
    print(f"  include_variants={result['include_variants']}")
    print(f"  variant_types={','.join(result['variant_types'])}")
    print(f"  inspected={result['inspected']}")
    print(f"  planned_uploads={result['planned_uploads']}")
    print(f"  skipped={result['skipped_count']}")

    for item in result.get("items") or []:
        print(
            "  - "
            f"{item['source_kind']} image#{item['product_image_id']} "
            f"product#{item['product_id']} type={item['variant_type']} "
            f"{item['source_url']} -> {item['target_path']} "
            f"({item['target_url']})"
        )

    skipped = result.get("skipped") or []
    if skipped:
        print("\nSkipped")
        for item in skipped[:20]:
            print(
                "  - "
                f"{item['source_kind']} image#{item['product_image_id']} "
                f"type={item['variant_type']} reason={item['skip_reason']} "
                f"url={item['source_url']}"
            )
        if len(skipped) > 20:
            print(f"  ... {len(skipped) - 20} more skipped rows")

    if result["dry_run"]:
        print("\nDry run only. Use --execute after reviewing this bounded plan.")
        return

    print(f"\nuploaded={result.get('uploaded', 0)}")
    print(f"updated_variants={result.get('updated_variants', 0)}")
    errors = result.get("errors") or []
    print(f"errors={len(errors)}")
    for item in errors:
        print(
            "  - "
            f"{item['source_kind']} image#{item['product_image_id']} "
            f"type={item['variant_type']} error={item['error']}"
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _validate_args(args, parser)

    execute = bool(args.execute and not args.dry_run)
    result = asyncio.run(
        run(
            execute=execute,
            provider=args.provider,
            limit=args.limit,
            product_id=args.product_id,
            after_image_id=args.after_image_id,
            from_image_id=args.from_image_id,
            to_image_id=args.to_image_id,
            include_originals=args.include_originals,
            include_variants=args.include_variants,
            variant_types=args.variant_type,
            include_non_ready=args.include_non_ready,
            force=args.force,
        )
    )
    _print_result(result)


if __name__ == "__main__":
    main()
