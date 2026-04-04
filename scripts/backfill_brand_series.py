import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker

sys.path.append(".")

from core.config import settings
from models import Product, Tag
from services.brand_series_service import sync_product_brand_series


async def run_backfill(*, dry_run: bool = False) -> None:
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
            if await sync_product_brand_series(
                session,
                product=product,
                specs=product.specs or {},
                title=product.title or "",
            ):
                changed += 1

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
    args = parser.parse_args()
    asyncio.run(run_backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
