import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import Tag, TagGroup


async def run(group_slugs: list[str]) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        groups = (
            await session.execute(select(TagGroup).where(TagGroup.slug.in_(group_slugs)))
        ).scalars().all()
        if not groups:
            print("No matching groups found.")
            return

        group_ids = [g.id for g in groups if g.id is not None]
        tags = (
            await session.execute(select(Tag).where(Tag.group_id.in_(group_ids)))
        ).scalars().all()

        hidden_groups = 0
        hidden_tags = 0
        for group in groups:
            if group.is_public:
                group.is_public = False
                hidden_groups += 1
        for tag in tags:
            if tag.is_public:
                tag.is_public = False
                hidden_tags += 1

        await session.commit()
        print(f"Hidden groups: {hidden_groups}, hidden tags: {hidden_tags}")
        print(f"Processed group slugs: {', '.join(group_slugs)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Soft-hide legacy technical tag groups/tags via is_public=false."
    )
    parser.add_argument(
        "--groups",
        nargs="+",
        default=["area"],
        help="TagGroup slugs to hide (default: area).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.groups))


if __name__ == "__main__":
    main()
