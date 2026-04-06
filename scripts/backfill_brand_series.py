import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker

sys.path.append(".")

from core.config import settings
from models import Product, Tag
from services.brand_series_service import sync_product_brand_series
from services.tag_logic import is_invalid_brand_name, is_invalid_brand_slug


def _strip_invalid_brand_specs(specs: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    cleaned = dict(specs or {})
    changed = False

    for key in ("brand", "Бренд", "Марка", "Производитель", "manufacturer"):
        if key in cleaned and is_invalid_brand_name(cleaned.get(key)):
            del cleaned[key]
            changed = True

    return cleaned, changed


def _remove_invalid_brand_tags(product: Product) -> tuple[list[Tag], bool, list[str]]:
    tags = list(product.tags or [])
    removed_titles: list[str] = []
    kept: list[Tag] = []
    changed = False

    for tag in tags:
        group_slug = getattr(getattr(tag, "group", None), "slug", None)
        if group_slug == "brand" and (
            is_invalid_brand_name(tag.title) or is_invalid_brand_slug(tag.slug)
        ):
            changed = True
            removed_titles.append(f"{tag.title} ({tag.slug})")
            continue
        kept.append(tag)

    return kept, changed, removed_titles


async def run_backfill(*, dry_run: bool = False, safe_brand_cleanup: bool = False) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        products = (
            await session.execute(
                select(Product).options(selectinload(Product.tags).selectinload(Tag.group))
            )
        ).scalars().all()

        changed = 0
        processed = 0
        for product in products:
            processed += 1
            row_changed = False
            data_specs = dict(product.specs or {})
            tag_list = list(product.tags or [])

            if safe_brand_cleanup:
                tag_list, tags_changed, removed_titles = _remove_invalid_brand_tags(product)
                if tags_changed:
                    product.tags = tag_list
                    row_changed = True
                    print(
                        f"[cleanup] product#{product.id} removed invalid brand tags: {', '.join(removed_titles)}"
                    )

                cleaned_specs, specs_changed = _strip_invalid_brand_specs(data_specs)
                if specs_changed:
                    product.specs = cleaned_specs
                    data_specs = cleaned_specs
                    row_changed = True
                    print(f"[cleanup] product#{product.id} stripped invalid brand specs")

            if await sync_product_brand_series(
                session,
                product=product,
                specs=data_specs,
                title=product.title or "",
                tags=tag_list,
            ):
                row_changed = True

            if row_changed:
                changed += 1
                session.add(product)

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    await engine.dispose()
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"[{mode}] processed={processed}, changed={changed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill product.brand_id and product.series_id")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit changes")
    parser.add_argument(
        "--safe-brand-cleanup",
        action="store_true",
        help="Remove only obvious pseudo-brand values before backfill (multisplit/system tokens).",
    )
    args = parser.parse_args()
    asyncio.run(
        run_backfill(
            dry_run=args.dry_run,
            safe_brand_cleanup=args.safe_brand_cleanup,
        )
    )


if __name__ == "__main__":
    main()
