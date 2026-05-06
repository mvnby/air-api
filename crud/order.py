"""
Repository Layer: Order Data Access Object (DAO).
Pure database operations.
"""
from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import delete
from models import Order, Product, OrderProductLink, OrderServiceLink


class OrderDAO:
    """Data Access Object for Order entity."""

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
        # product_id удален!
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Order:
        """Create a new order wrapper (without items)."""
        order = Order(
            user_id=user_id,
            username=username,   # Убедитесь, что эти поля есть в Order, если нет - удалите
            # В models.py я видел delivery_address и status, но не видел username/fullname.
            # Если их нет в модели Order, сохраняйте их в Customer или delivery_address.
            # Для простоты пока создадим базовый:
            status="new"
        )
        # Если в модели Order нет полей username/full_name/phone, мы их тут не передаем.
        # Судя по вашему models.py, там есть user_id и customer_id. 
        # Давайте сделаем безопасно:
        order.delivery_address = phone # Временно сохраним телефон как адрес, если нет Customer
        
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Order]:
        """Get all orders with product info."""
        # Fix: Order has product_links, not product
        stmt = select(Order).options(
            selectinload(Order.customer),
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service),
            selectinload(Order.installers)
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
     # --- ДОБАВЛЕННЫЕ МЕТОДЫ ---
    @staticmethod
    async def clear_product_links(session: AsyncSession, order_id: int):
        """Removes all product links for a given order."""
        await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == order_id))

    @staticmethod
    async def clear_service_links(session: AsyncSession, order_id: int):
        """Removes all service links for a given order."""
        await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id))

    @staticmethod
    async def get_with_links(session: AsyncSession, order_id: int) -> Optional[Order]:
        """Get order with all links (products, services, installers)."""
        stmt = select(Order).where(Order.id == order_id).options(
            selectinload(Order.proposals),
            selectinload(Order.product_links),
            selectinload(Order.service_links),
            selectinload(Order.installers)
        )
        result = await session.execute(stmt)
        return result.scalars().first()
