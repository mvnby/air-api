#!/usr/bin/env python3
"""
Quick verification that the new columns exist in the database.
"""
import asyncio
import sys
import os

sys.path.append(os.getcwd())

from core.database import async_session_maker
from sqlalchemy import text

async def verify_schema():
    print("🔍 Verifying database schema...")
    
    async with async_session_maker() as session:
        # Query to check columns
        result = await session.execute(text("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'order_product_link' 
            AND column_name IN ('is_installation_included', 'installation_price', 'installation_details')
            ORDER BY column_name;
        """))
        
        columns = result.fetchall()
        
        print("\n✅ New columns in order_product_link table:")
        for col in columns:
            print(f"   - {col[0]}: {col[1]} (nullable: {col[2]})")
        
        if len(columns) == 3:
            print("\n🎉 SUCCESS! All snapshot pricing columns exist!")
            return True
        else:
            print(f"\n❌ FAILED! Expected 3 columns, found {len(columns)}")
            return False

if __name__ == "__main__":
    try:
        success = asyncio.run(verify_schema())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
