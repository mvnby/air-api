#!/usr/bin/env python3
"""Quick verification script to check slug migration results"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select
from models import Product
from core.database import async_session_maker

async def verify():
    session = async_session_maker()
    stmt = select(Product).limit(10)
    result = await session.execute(stmt)
    products = result.scalars().all()
    
    print("Sample products with slugs:")
    print("-" * 60)
    for p in products:
        print(f"{p.id:3d}: {p.title[:40]:40s} → {p.slug}")
    print("-" * 60)
    
    await session.close()

if __name__ == "__main__":
    asyncio.run(verify())
