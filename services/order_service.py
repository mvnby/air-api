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

    @staticmethod
    async def update_order_links(order_id: int, items_data: Dict[str, Any]) -> None:
        """
        Update order product and service links.
        
        Args:
            order_id: The ID of the order to update.
            items_data: Dictionary containing 'products' and 'services' lists.
        """
        from models import OrderProductLink, OrderServiceLink
        from core.database import async_session_maker
        from sqlalchemy import delete

        async with async_session_maker() as session:
            # 1. Clear existing links for this order
            await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == order_id))
            await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id))
            
            # 2. Add new product links
            for p in items_data.get("products", []):
                link = OrderProductLink(
                    order_id=order_id,
                    product_id=p["product_id"],
                    quantity=p["quantity"],
                    price=p["price"]
                )
                session.add(link)
            
            # 3. Add new service links
            for s in items_data.get("services", []):
                link = OrderServiceLink(
                    order_id=order_id,
                    service_id=s["service_id"],
                    quantity=s["quantity"],
                    price=s["price"]
                )
                session.add(link)
            
            await session.commit()
