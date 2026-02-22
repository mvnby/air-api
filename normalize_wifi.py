import asyncio
import os
import sys

# Add current dir to pythonpath
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import async_session_maker
from models.product import Product
from sqlalchemy import select

async def unify_wifi_keys():
    async with async_session_maker() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        updated_count = 0
        for p in products:
            if p.specs and 'wifi-ready' in p.specs:
                p.specs['wifi_ready'] = p.specs.pop('wifi-ready')
                p.specs = dict(p.specs)
                updated_count += 1
                
        if updated_count > 0:
            await session.commit()
            print(f"Updated {updated_count} products.")
        else:
            print("No updates needed.")

if __name__ == "__main__":
    asyncio.run(unify_wifi_keys())
