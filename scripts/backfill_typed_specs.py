"""Refresh internal typed/filter specs for existing products.

Default mode is dry-run. Use --execute for bounded writes only.
The command intentionally preserves public flat spec fields.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

sys.path.append(".")

from core.database import async_session_maker  # noqa: E402
from models import Product, Tag  # noqa: E402
from services.spec_typed_backfill_service import (  # noqa: E402
    INTERNAL_SPEC_KEYS,
    build_specs_with_typed_internal_layer,
)


def _changed_internal_keys(old_specs: dict[str, Any], new_specs: dict[str, Any]) -> list[str]:
    return [key for key in INTERNAL_SPEC_KEYS if old_specs.get(key) != new_specs.get(key)]


async def run(
    *,
    execute: bool,
    limit: int,
    product_id: int | None,
    strict_wifi_from_tags: bool,
) -> dict[str, Any]:
    query = select(Product).options(selectinload(Product.tags).selectinload(Tag.group)).order_by(Product.id)
    if product_id is not None:
        query = query.where(Product.id == product_id)
    if limit:
        query = query.limit(limit)

    async with async_session_maker() as session:
        products = (await session.execute(query)).scalars().all()
        changed = 0
        samples: list[dict[str, Any]] = []

        for product in products:
            old_specs = dict(product.specs or {})
            wifi_tag_slugs = [
                tag.slug
                for tag in (product.tags or [])
                if tag.slug in {"wifi-builtin", "wifi-ready"}
            ]
            new_specs = build_specs_with_typed_internal_layer(
                old_specs,
                wifi_tag_slugs=wifi_tag_slugs,
                strict_wifi_from_tags=strict_wifi_from_tags,
                title=product.title or "",
            )
            if new_specs == old_specs:
                continue

            changed += 1
            changed_keys = _changed_internal_keys(old_specs, new_specs)
            typed_specs = new_specs.get("__typed_specs") or {}
            if len(samples) < 20:
                samples.append(
                    {
                        "id": product.id,
                        "slug": product.slug,
                        "title": product.title,
                        "changed_internal_keys": changed_keys,
                        "typed_keys_count": len(typed_specs) if isinstance(typed_specs, dict) else 0,
                        "typed_keys_sample": list(typed_specs.keys())[:12] if isinstance(typed_specs, dict) else [],
                    }
                )

            if execute:
                product.specs = new_specs
                flag_modified(product, "specs")
                session.add(product)

        if execute:
            await session.commit()
        else:
            await session.rollback()

    return {
        "mode": "execute" if execute else "dry_run",
        "processed": len(products),
        "changed": changed,
        "limit": limit,
        "product_id": product_id,
        "strict_wifi_from_tags": strict_wifi_from_tags,
        "samples": samples,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill only internal typed/filter catalog spec keys for existing products. "
            "Public flat specs are preserved."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist specs updates. Without this flag the command only prints a plan.",
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
        help="Maximum products to inspect in this run (1-5000, default: 500).",
    )
    parser.add_argument("--product-id", type=int, default=None, help="Inspect/update one product only.")
    parser.add_argument(
        "--strict-wifi-from-tags",
        action="store_true",
        help="Treat Wi-Fi tags as authoritative when rebuilding internal Wi-Fi filters.",
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
            product_id=args.product_id,
            strict_wifi_from_tags=args.strict_wifi_from_tags,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

