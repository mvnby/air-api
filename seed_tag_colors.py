import asyncio
from sqlmodel import select
from database import async_session_maker
from models import TagGroup

async def seed_colors():
    async with async_session_maker() as session:
        # 1. Area -> blue (info)
        # 2. Inverter -> green (success)
        # 3. Brand -> purple (primary)
        
        result = await session.execute(select(TagGroup))
        groups = result.scalars().all()
        for group in groups:
            ltitle = group.title.lower()
            if "площадь" in ltitle or "area" in ltitle:
                group.color = "info"
            elif "инвертор" in ltitle or "technology" in ltitle:
                group.color = "success"
            elif "бренд" in ltitle or "brand" in ltitle:
                group.color = "primary"
            else:
                group.color = "secondary"
                
            session.add(group)
        await session.commit()
        print("Colors seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_colors())

if __name__ == "__main__":
    asyncio.run(seed_colors())
