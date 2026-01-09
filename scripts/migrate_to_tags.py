import asyncio
from database import engine
from sqlmodel import text

async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE category RENAME TO _old_category"))
            await conn.execute(text("ALTER TABLE productcategorylink RENAME TO _old_productcategorylink"))
            print("Renamed old tables.")
        except Exception as e:
            print(f"Rename failed (maybe already renamed): {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
