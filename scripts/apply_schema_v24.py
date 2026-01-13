#!/usr/bin/env python
"""
Phase 24 Schema Migration: Customer Model
- Truncates Order table (test data only!)
- Creates Customer table
- Modifies Order table to use customer_id FK
"""
import asyncio
from sqlalchemy import text
from core.database import engine

async def main():
    async with engine.begin() as conn:
        print("Phase 24: Customer Model Migration")
        print("=" * 50)
        
        # 1. Truncate order table and related links
        print("1. Truncating order-related tables...")
        await conn.execute(text("DELETE FROM order_product_link"))
        await conn.execute(text("DELETE FROM order_service_link"))
        await conn.execute(text('DELETE FROM "order"'))
        print("   ✓ Orders truncated")
        
        # 2. Create customer table (SQLite syntax)
        print("2. Creating customer table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                type TEXT DEFAULT 'individual',
                full_legal_name TEXT,
                inn TEXT,
                kpp TEXT,
                legal_address TEXT,
                actual_address TEXT,
                bank_name TEXT,
                bic TEXT,
                iban TEXT,
                signer_position TEXT DEFAULT 'Генерального директора',
                signer_name TEXT,
                acting_basis TEXT DEFAULT 'Устава',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customer_name ON customer(name)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customer_phone ON customer(phone)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customer_inn ON customer(inn)"))
        print("   ✓ Customer table created")
        
        # 3. Modify order table - SQLite requires table recreation for schema changes
        print("3. Checking and updating order table...")
        
        # Check existing columns
        result = await conn.execute(text("PRAGMA table_info('order')"))
        columns = {row[1] for row in result.fetchall()}
        
        if 'customer_id' not in columns:
            # Need to recreate table
            print("   Recreating order table with new schema...")
            
            # Create new table
            await conn.execute(text("""
                CREATE TABLE order_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER REFERENCES customer(id) ON DELETE SET NULL,
                    delivery_address TEXT,
                    user_id INTEGER,
                    status TEXT DEFAULT 'new',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Drop old table and rename (no data since we truncated)
            await conn.execute(text('DROP TABLE "order"'))
            await conn.execute(text('ALTER TABLE order_new RENAME TO "order"'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_user_id ON "order"(user_id)'))
            print("   ✓ Order table recreated")
        else:
            print("   ✓ Order table already has customer_id")
        
        print("\n" + "=" * 50)
        print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(main())
