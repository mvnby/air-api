"""
Repository Layer: Order Data Access Object (DAO).
Pure database operations.
"""
from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Order, Product


class OrderDAO:
    """Data Access Object for Order entity."""

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
        product_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Order:
        """Create a new order."""
        order = Order(
            user_id=user_id,
            product_id=product_id,
            username=username,
            full_name=full_name,
            phone=phone
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Order]:
        """Get all orders with product info."""
        stmt = select(Order).options(
            selectinload(Order.product)
        ).order_by(Order.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: str) -> bool:
        """Update order status. Returns True if successful."""
        order = await session.get(Order, order_id)
        if order:
            order.status = new_status
            session.add(order)
            await session.commit()
            return True
        return False
