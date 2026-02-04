import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
import sys
import os

sys.path.append('.')
from core.config import settings
from models import Product

async def clear_legacy_images():
    # Use sync driver for migration style tasks if needed, but we keep it async as per stack
    db_url = settings.DATABASE_URL
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("🚀 Starting legacy image cleanup...")
    
    async with async_session() as session:
        # Fetch all products
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        updated_count = 0
        total_removed = 0
        
        for p in products:
            if p.images and len(p.images) > 0:
                total_removed += len(p.images)
                # Set legacy images field to empty list
                p.images = []
                flag_modified(p, "images")
                updated_count += 1
        
        if updated_count > 0:
            await session.commit()
            print(f"✅ Cleared legacy images for {updated_count} products. Removed {total_removed} references.")
        else:
            print("ℹ️ No legacy images found to clear.")

if __name__ == "__main__":
    asyncio.run(clear_legacy_images())
