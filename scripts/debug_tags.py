import asyncio
from core.database import get_session
from models.product import TagGroup, Tag
from sqlmodel import select

async def run():
    async for session in get_session():
        # Get groups
        groups_stmt = select(TagGroup)
        groups = (await session.execute(groups_stmt)).scalars().all()
        print("GROUPS:")
        for g in groups:
            print(f" - {g.title} (slug: {g.slug}, id: {g.id})")
        
        # Get tags count per group
        tags_stmt = select(Tag)
        tags = (await session.execute(tags_stmt)).scalars().all()
        print("\nTAGS (first 20):")
        for t in tags[:20]:
            print(f" - {t.title} (slug: {t.slug}, id: {t.id}, group_id: {t.group_id})")
        break

if __name__ == "__main__":
    asyncio.run(run())
