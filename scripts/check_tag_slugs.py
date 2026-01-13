from core.database import async_session_maker
from models import Tag
from sqlalchemy import select
import asyncio

async def fix_duplicate_slugs():
    async with async_session_maker() as session:
        # Get all tags
        result = await session.execute(select(Tag))
        tags = result.scalars().all()
        
        slug_counts = {}
        duplicates_found = 0
        
        for tag in tags:
            if tag.slug in slug_counts:
                duplicates_found += 1
                slug_counts[tag.slug] += 1
                new_slug = f"{tag.slug}-{slug_counts[tag.slug]}"
                print(f"Fixing duplicate slug: '{tag.slug}' -> '{new_slug}' (Tag ID: {tag.id})")
                tag.slug = new_slug
            else:
                slug_counts[tag.slug] = 0
        
        if duplicates_found > 0:
            await session.commit()
            print(f"Success: Fixed {duplicates_found} duplicate slugs.")
        else:
            print("No duplicate slugs found. Schema update is safe.")

if __name__ == "__main__":
    asyncio.run(fix_duplicate_slugs())
