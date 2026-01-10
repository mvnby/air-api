import asyncio
from database import init_db, async_session_maker
from models import Tag
from sqlmodel import select

async def main():
    await init_db()
    async with async_session_maker() as session:
        result = await session.execute(select(Tag))
        tags = result.scalars().all()
        print(f"Total tags: {len(tags)}")
        for t in tags:
            print(f"ID: {t.id} | Title: {t.title}")

if __name__ == "__main__":
    asyncio.run(main())
