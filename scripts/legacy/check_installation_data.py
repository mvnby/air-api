#!/usr/bin/env python3
import asyncio
from core.database import async_session_maker
from sqlalchemy import text

async def check_orders():
    async with async_session_maker() as session:
        result = await session.execute(text("""
            SELECT id, order_id, product_id, is_installation_included, installation_price 
            FROM order_product_link 
            ORDER BY id DESC 
            LIMIT 5
        """))
        
        print("\n📊 Последние 5 записей order_product_link:")
        print(f"{'ID':<6} | {'Order ID':<10} | {'Product ID':<12} | {'Installation':<12} | {'Price':<10}")
        print("-" * 70)
        
        for row in result.fetchall():
            print(f"{row[0]:<6} | {row[1]:<10} | {row[2]:<12} | {row[3]!s:<12} | {row[4]:<10}")

if __name__ == "__main__":
    asyncio.run(check_orders())
