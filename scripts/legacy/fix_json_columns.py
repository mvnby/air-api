import asyncio
import ast
import json
from sqlmodel import select
from core.database import async_session_maker
from models import Product

async def fix_json_data():
    async with async_session_maker() as session:
        stmt = select(Product)
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        updated_count = 0
        for product in products:
            needs_update = False
            
            # Fix specs
            if isinstance(product.specs, str):
                try:
                    # Try to parse Python-like string representation
                    val = ast.literal_eval(product.specs)
                    product.specs = val
                    needs_update = True
                except Exception as e:
                    print(f"Error parsing specs for product {product.id}: {e}")
            
            # Fix images
            if isinstance(product.images, str):
                try:
                    val = ast.literal_eval(product.images)
                    product.images = val
                    needs_update = True
                except Exception as e:
                    print(f"Error parsing images for product {product.id}: {e}")
            
            if needs_update:
                session.add(product)
                updated_count += 1
        
        await session.commit()
        print(f"Fixed {updated_count} products.")

if __name__ == "__main__":
    asyncio.run(fix_json_data())
