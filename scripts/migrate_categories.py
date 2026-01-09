import asyncio
import json
import slugify
import aiosqlite

DB_PATH = "air_conditioners.db"

async def migrate():
    print(f"Starting migration on {DB_PATH}...")
    
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Create tables if they don't exist (using raw SQL to be safe regardless of ORM state)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL UNIQUE,
                slug VARCHAR NOT NULL
            );
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS ix_category_name ON category (name);")
        await db.execute("CREATE INDEX IF NOT EXISTS ix_category_slug ON category (slug);")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS productcategorylink (
                product_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY (product_id, category_id),
                FOREIGN KEY(product_id) REFERENCES product(id),
                FOREIGN KEY(category_id) REFERENCES category(id)
            );
        """)
        
        # 2. Read products with old formatted categories
        # Note: SQLModel might have renamed the column or we just need to read it as raw string.
        # Let's check columns first.
        cursor = await db.execute("PRAGMA table_info(product)")
        columns = await cursor.fetchall()
        col_names = [c[1] for c in columns]
        
        if "categories" not in col_names:
            print("Column 'categories' not found in product table. Migration probably already done or schema mismatch.")
            return

        print("Reading existing products...")
        async with db.execute("SELECT id, categories FROM product") as cursor:
            products = await cursor.fetchall()
            
        print(f"Found {len(products)} products.")
        
        for pid, cats_json in products:
            if not cats_json:
                continue
                
            try:
                cats_list = json.loads(cats_json)
            except json.JSONDecodeError:
                print(f"Skipping product {pid}: invalid JSON in categories")
                continue
                
            if not isinstance(cats_list, list):
                continue
                
            for cat_name in cats_list:
                cat_name = cat_name.strip()
                if not cat_name: continue
                
                # Create or Get Category
                slug = slugify.slugify(cat_name)
                
                # Try insert (ignore if exists)
                try:
                    await db.execute("INSERT OR IGNORE INTO category (name, slug) VALUES (?, ?)", (cat_name, slug))
                except Exception as e:
                    print(f"Error inserting category {cat_name}: {e}")
                
                # Get ID
                async with db.execute("SELECT id FROM category WHERE name = ?", (cat_name,)) as c:
                    row = await c.fetchone()
                    if row:
                        cat_id = row[0]
                        # Link
                        await db.execute("INSERT OR IGNORE INTO productcategorylink (product_id, category_id) VALUES (?, ?)", (pid, cat_id))
        
        await db.commit()
        
        # Optional: Drop old column? 
        # SQLite doesn't support DROP COLUMN easily in older versions, and SQLModel expects it to NOT be there if we removed it from model?
        # Actually, since we updated the model to Relation, SQLModel won't query 'categories' column anymore, it uses the link table.
        # But for safety, we leave the column or rename it.
        # print("Migration finished. Old 'categories' column checks out.")

if __name__ == "__main__":
    # installing slugify if not present: pip install python-slugify
    try:
        import slugify
    except ImportError:
        print("Please run: pip install python-slugify")
        exit(1)
        
    asyncio.run(migrate())
