import asyncio
import aiosqlite

DB_PATH = "air_conditioners.db"

async def reset():
    print(f"Resetting categories in {DB_PATH}...")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM productcategorylink")
        await db.execute("DELETE FROM category")
        await db.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = 'category'")
        await db.commit()
    print("Categories and links cleared. Link table empty.")

if __name__ == "__main__":
    asyncio.run(reset())
