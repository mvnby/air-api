import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import ProductTagLink, Tag, TagGroup


TARGET_GROUPS = ("area", "compressor-type")


async def run() -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        summary_stmt = (
            select(
                TagGroup.slug,
                func.count(ProductTagLink.product_id),
            )
            .join(Tag, Tag.group_id == TagGroup.id)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .where(TagGroup.slug.in_(TARGET_GROUPS))
            .group_by(TagGroup.slug)
            .order_by(TagGroup.slug)
        )
        rows = (await session.execute(summary_stmt)).all()

        print("Legacy link summary:")
        if not rows:
            print("  No links found for target groups.")
        for slug, count in rows:
            print(f"  {slug}: {count}")

        details_stmt = (
            select(
                TagGroup.slug,
                Tag.slug,
                func.count(ProductTagLink.product_id),
            )
            .join(Tag, Tag.group_id == TagGroup.id)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .where(TagGroup.slug.in_(TARGET_GROUPS))
            .group_by(TagGroup.slug, Tag.slug)
            .order_by(TagGroup.slug, Tag.slug)
        )
        detail_rows = (await session.execute(details_stmt)).all()
        print("\nBy tag:")
        for group_slug, tag_slug, count in detail_rows:
            print(f"  {group_slug}:{tag_slug} -> {count}")


if __name__ == "__main__":
    asyncio.run(run())
