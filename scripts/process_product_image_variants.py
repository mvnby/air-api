"""Safely process ProductImageVariant records from the command line.

Default mode is dry-run. Use --execute for bounded writes only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(".")

from services.product_image_processing_contract import (  # noqa: E402
    ProductImageProcessingProvider,
    ProductImageVariantType,
)
from services.product_image_variant_service import ProductImageVariantService  # noqa: E402


PROCESSABLE_VARIANTS = (
    ProductImageVariantType.PROCESSED.value,
    ProductImageVariantType.CARD.value,
    ProductImageVariantType.FULL.value,
)
CLI_PROVIDERS = (
    ProductImageProcessingProvider.AUTO.value,
    ProductImageProcessingProvider.NOOP.value,
    ProductImageProcessingProvider.MANUAL.value,
    ProductImageProcessingProvider.REMBG.value,
    ProductImageProcessingProvider.BIREFNET.value,
    ProductImageProcessingProvider.BEN.value,
)


async def process_product_image_variants(
    *,
    session: AsyncSession,
    execute: bool,
    limit: int,
    product_id: int | None,
    variant_type: str,
    provider: str,
    rembg_model: str | None,
    include_installation: bool,
    only_missing: bool,
    retry_failed: bool,
) -> dict[str, Any]:
    return await ProductImageVariantService.process_missing_variants(
        session=session,
        variant_type=variant_type,
        limit=limit,
        include_installation=include_installation,
        dry_run=not execute,
        provider=provider,
        rembg_model=rembg_model,
        product_id=product_id,
        only_missing=only_missing,
        retry_failed=retry_failed,
    )


async def run(
    *,
    execute: bool,
    limit: int,
    product_id: int | None,
    variant_type: str,
    provider: str,
    rembg_model: str | None,
    include_installation: bool,
    only_missing: bool,
    retry_failed: bool,
) -> dict[str, Any]:
    from core.database import async_session_maker

    async with async_session_maker() as session:
        return await process_product_image_variants(
            session=session,
            execute=execute,
            limit=limit,
            product_id=product_id,
            variant_type=variant_type,
            provider=provider,
            rembg_model=rembg_model,
            include_installation=include_installation,
            only_missing=only_missing,
            retry_failed=retry_failed,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare missing or failed product image variants. "
            "Dry-run is the default; pass --execute to persist a bounded batch."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist processing results. Without this flag the command only prints candidates.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode. This is already the default.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum images to inspect/process in this run (1-100, default: 20).",
    )
    parser.add_argument(
        "--product-id",
        type=int,
        default=None,
        help="Limit candidates to one product id.",
    )
    parser.add_argument(
        "--variant-type",
        choices=PROCESSABLE_VARIANTS,
        default=ProductImageVariantType.CARD.value,
        help="Variant to prepare.",
    )
    parser.add_argument(
        "--only-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Include images with no variant row. This is the default safe selection; "
            "use --no-only-missing with --retry-failed to target failed rows only."
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also include existing failed variants for the selected type.",
    )
    parser.add_argument(
        "--provider",
        choices=CLI_PROVIDERS,
        default=ProductImageProcessingProvider.NOOP.value,
        help=(
            "Processing provider. noop means local Pillow normalization without background "
            "removal; auto uses BACKGROUND_REMOVAL_PROVIDER."
        ),
    )
    parser.add_argument(
        "--rembg-model",
        default=None,
        help=(
            "Optional rembg model override, for example u2net, isnet-general-use, "
            "birefnet-general. Applies when provider resolves to rembg."
        ),
    )
    parser.add_argument(
        "--include-installation",
        action="store_true",
        help="Include installation photos. Catalog variants skip them by default.",
    )
    return parser


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run cannot be used together")
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")
    if args.product_id is not None and args.product_id < 1:
        parser.error("--product-id must be a positive integer")


def _print_result(result: dict[str, Any], *, execute: bool, provider: str) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print("Product Image Variant Worker")
    print(f"  mode={mode}")
    print(f"  variant_type={result['variant_type']}")
    print(f"  provider={provider}")
    print(f"  total_candidates={result.get('total_candidates', 0)}")
    print(f"  returned={result.get('returned', 0)}")

    candidates = result.get("candidates") or []
    for item in candidates:
        print(
            "  - "
            f"image#{item['product_image_id']} product#{item['product_id']} "
            f"reason={item['reason']} url={item['url']}"
        )

    if not execute:
        print("\nDry run only. Use --execute to persist this bounded batch.")
        return

    print(f"\nprocessed={result.get('processed', 0)}")
    errors = result.get("errors") or []
    print(f"errors={len(errors)}")
    for item in errors:
        print(
            "  - "
            f"image#{item.get('product_image_id')} "
            f"status={item.get('status', 'failed')} error={item.get('error')}"
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _validate_args(args, parser)

    execute = bool(args.execute and not args.dry_run)
    result = asyncio.run(
        run(
            execute=execute,
            limit=args.limit,
            product_id=args.product_id,
            variant_type=args.variant_type,
            provider=args.provider,
            rembg_model=args.rembg_model,
            include_installation=args.include_installation,
            only_missing=args.only_missing,
            retry_failed=args.retry_failed,
        )
    )
    _print_result(result, execute=execute, provider=args.provider)


if __name__ == "__main__":
    main()
