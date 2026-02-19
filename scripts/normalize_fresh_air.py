import asyncio
from sqlalchemy.future import select

from core.database import async_session_maker
from models.product import Product

async def main():
    async with async_session_maker() as session:
        result = await session.execute(
            select(Product)
        )
        products = result.scalars().all()
        found = 0
        for p in products:
            p_specs = p.specs
            if not p_specs: continue
            
            if p_specs.get("fresh_air"):
                continue

            # check if Свойства contains "Приток свежего воздуха"
            val = p_specs.get("Приток свежего воздуха")
            if val and str(val).lower() in ["да", "yes", "true", "1", "есть"]:
                new_specs = dict(p_specs)
                new_specs["fresh_air"] = True
                p.specs = new_specs
                session.add(p)
                found += 1
                title = getattr(p, "title", str(p.id))
                print(f"Product {p.id}: {title} updated!")
                
            props = p_specs.get("Свойства", "")
            if isinstance(props, str) and "Приток свежего воздуха" in props:
                new_specs = dict(p_specs)
                new_specs["fresh_air"] = True
                p.specs = new_specs
                session.add(p)
                found += 1
                title = getattr(p, "title", str(p.id))
                print(f"Product {p.id}: {title} updated!")
            elif isinstance(props, list) and any("Приток свежего воздуха" in str(x) for x in props):
                new_specs = dict(p_specs)
                new_specs["fresh_air"] = True
                p.specs = new_specs
                session.add(p)
                found += 1
                title = getattr(p, "title", str(p.id))
                print(f"Product {p.id}: {title} updated!")

        if found > 0:
            await session.commit()
        print(f"Normalized {found} products")

if __name__ == "__main__":
    asyncio.run(main())
