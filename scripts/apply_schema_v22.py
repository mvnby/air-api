"""
Migration script for Phase 22.
Drops the old 'order' table and recreates it along with new CRM-related tables.
"""
import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import SQLModel, text
from core.database import engine
import models # Ensure all models are registered in metadata

async def migrate():
    print("--- Starting Phase 22 Migration ---")
    
    async with engine.begin() as conn:
        print("Truncating old 'order' table (and related indices)...")
        # We drop the order table because the schema change is drastic
        # Favorite table also has a foreign key to product, and Order had one too.
        # SQLite doesn't support easy DROP COLUMN/ALTER TABLE for multiple changes.
        await conn.execute(text("DROP TABLE IF EXISTS \"order\""))
        
        print("Creating new tables: service, order, order_product_link, order_service_link...")
        # SQLModel.metadata.create_all ignores already existing tables (Product, Tag, etc.)
        await conn.run_sync(SQLModel.metadata.create_all)
        
    print("--- Migration Successful! ---")
    print("New models created: Service, Order, OrderProductLink, OrderServiceLink.")
    print("Existing data in Product, Tag, TagGroup and Favorite remains intact.")

if __name__ == "__main__":
    asyncio.run(migrate())
