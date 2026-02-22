import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import async_session_maker
from models.product import Product
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

async def inspect():
    async with async_session_maker() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        found = 0
        updated = 0
        for p in products:
            if not p.specs:
                continue
                
            keys = list(p.specs.keys())
            has_dash = 'wifi-ready' in keys
            has_under = 'wifi_ready' in keys
            
            if has_dash:
                found += 1
                val_dash = p.specs['wifi-ready']
                val_under = p.specs.get('wifi_ready')
                
                print(f"Product {p.id}: wifi-ready={val_dash}, wifi_ready={val_under}")
                
                # Let's fix it properly
                # If wifi_ready is not there, or if we want to merge them
                # Both might be boolean or strings. Let's take True if any is true.
                
                # Helper to convert to bool
                def is_t(v):
                    if isinstance(v, bool): return v
                    if isinstance(v, str): return v.lower() in ('true', 'yes', 'да', 'ready', '1', '+')
                    return False
                
                combined_val = is_t(val_dash) or is_t(val_under)
                
                # Delete the dash one
                del p.specs['wifi-ready']
                
                # Create the underscore one
                p.specs['wifi_ready'] = combined_val
                
                # Notify SQLAlchemy of the mutation
                flag_modified(p, "specs")
                updated += 1
                
        if updated > 0:
            await session.commit()
            print(f"Fixed {updated} products.")
        else:
            print("No products with 'wifi-ready' found.")

if __name__ == "__main__":
    asyncio.run(inspect())
