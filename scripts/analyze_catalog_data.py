import asyncio
from core.database import get_session
from models.product import Product
from sqlmodel import select

async def run():
    async for session in get_session():
        stmt = select(Product.specs, Product.title)
        result = await session.execute(stmt)
        rows = result.all()
        
        indoor_types = set()
        product_types = set()
        brands = set()
        
        for specs, title in rows:
            if specs:
                it = specs.get('indoor_type')
                if it: indoor_types.add(it)
                
                pt = specs.get('type')
                if pt: product_types.add(pt)
            
            if title:
                brand = title.split()[0]
                brands.add(brand)
        
        print("INDOOR TYPES:")
        for t in sorted(indoor_types): print(f" - {t}")
        
        print("\nPRODUCT TYPES:")
        for t in sorted(product_types): print(f" - {t}")
        
        print("\nBRANDS (from title first word):")
        for b in sorted(brands): print(f" - {b}")
        break

if __name__ == "__main__":
    asyncio.run(run())
