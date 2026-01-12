"""
Service Layer: Order Business Logic.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from crud.order import OrderDAO
from crud.product import ProductDAO
from models import Order


class OrderService:
    """Order business logic service."""

    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        product_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Order:
        """Create a new order."""
        return await OrderDAO.create(
            session,
            user_id=user_id,
            product_id=product_id,
            username=username,
            full_name=full_name,
            phone=phone
        )

    @staticmethod
    async def get_all_orders(session: AsyncSession) -> List[Order]:
        """Get all orders."""
        return await OrderDAO.get_all(session)

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: str) -> bool:
        """Update order status."""
        return await OrderDAO.update_status(session, order_id, new_status)
