
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from core.database import async_session_maker
from crud.order import OrderDAO
from models import Order

async def main():
    async with async_session_maker() as session:
        print("Fetching all orders...")
        # We need to fetch all orders using a query that doesn't eagerly load relations
        # and then process them one by one using get_with_links to ensure correct loading
        from sqlmodel import select
        stmt = select(Order.id)
        result = await session.execute(stmt)
        order_ids = result.scalars().all()
        
        print(f"Found {len(order_ids)} orders. Recalculating totals...")
        
        for oid in order_ids:
            order = await OrderDAO.get_with_links(session, oid)
            if order:
                old_total = order.total_amount
                order.calculate_totals()
                session.add(order)
                print(f"Order #{oid}: {old_total} -> {order.total_amount}")
        
        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
