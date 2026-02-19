import asyncio
from sqlalchemy.future import select

from core.database import async_session_maker
from models.product import Product

async def main():
    async with async_session_maker() as session:
        result = await session.execute(
            select(Product.id, Product.name, Product.specs)
        )
        products = result.all()
        found = 0
        for p_id, p_name, p_specs in products:
            if not p_specs: continue
            
            # recursive search for the string
            def search_dict(d):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if "Приток свежего воздуха" in str(k) or "Приток свежего воздуха" in str(v):
                            return True
                        if isinstance(v, (dict, list)):
                            if search_dict(v): return True
                elif isinstance(d, list):
                    for item in d:
                        if search_dict(item): return True
                return False

            if search_dict(p_specs):
                print(f"Product {p_id}: {p_name} -> {p_specs.get('Свойства') or p_specs}")
                # And update the spec
                if "Свойства" in p_specs:
                    if "Приток свежего воздуха" in p_specs["Свойства"]:
                        p_specs["fresh_air"] = True
                        session.add(Product(id=p_id, specs=p_specs))
                found += 1
                if found >= 5:
                    break
        
        # Save changes if we modified any
        await session.commit()
        print(f"Normailzed {found} products")

asyncio.run(main())
