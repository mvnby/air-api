import argparse
import asyncio
import sys

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import ProductTagLink, Tag, TagGroup


TARGET_GROUPS = ("area", "compressor-type")


async def run(execute: bool) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        target_tag_ids = (
            await session.execute(
                select(Tag.id).join(TagGroup, Tag.group_id == TagGroup.id).where(
                    TagGroup.slug.in_(TARGET_GROUPS)
                )
            )
        ).scalars().all()

        if not target_tag_ids:
            print("No target tags found.")
            return

        count_stmt = select(ProductTagLink).where(ProductTagLink.tag_id.in_(target_tag_ids))
        links = (await session.execute(count_stmt)).scalars().all()
        print(f"Found {len(links)} product_tag_link rows for {TARGET_GROUPS}.")

        if not execute:
            print("Dry run only. Use --execute to delete.")
            return

        await session.execute(
            delete(ProductTagLink).where(ProductTagLink.tag_id.in_(target_tag_ids))
        )
        await session.commit()
        print("Deleted legacy links.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete legacy product_tag_link rows for area/compressor-type."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute delete. Without this flag script runs in dry-run mode.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.execute))


if __name__ == "__main__":
    main()
