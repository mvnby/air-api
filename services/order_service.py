from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from crud.order import OrderDAO
from models import Order, OrderProductLink, OrderServiceLink

class OrderService:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        contact_info: str, # Телефон или адрес
        items_data: Dict[str, Any], # Словарь с товарами
        username: Optional[str] = None,
        full_name: Optional[str] = None
    ) -> Order:
        """
        Create order and populate it with items.
        """
        # 1. Создаем сам заказ
        order = await OrderDAO.create(
            session,
            user_id=user_id,
            phone=contact_info,
            username=username,
            full_name=full_name
        )
        
        # 2. Наполняем товарами
        if items_data:
            await OrderService.update_order_links(session, order.id, items_data)
        
        return order

    @staticmethod
    async def update_order_links(session: AsyncSession, order_id: int, items_data: Dict[str, Any]) -> None:
        """
        Full sync of order items (products/services).
        Uses current DB prices for products.
        """
        # 1. Очищаем старые связи
        await OrderDAO.clear_product_links(session, order_id)
        await OrderDAO.clear_service_links(session, order_id)
        
        # 2. Добавляем товары
        for p in items_data.get("products", []):
            link = OrderProductLink(
                order_id=order_id,
                product_id=p["product_id"],
                quantity=p["quantity"],
                price=p["price"] # Цена должна приходить актуальная
            )
            session.add(link)
        
        # 3. Добавляем услуги
        for s in items_data.get("services", []):
            link = OrderServiceLink(
                order_id=order_id,
                service_id=s["service_id"],
                quantity=s["quantity"],
                price=s["price"]
            )
            session.add(link)
            
        # session.add_all(new_links) - Removed as items are added in loop
        await session.flush() # Ensure links are in DB

        # 4. Пересчитываем итоговые цифры заказа
        # Необходимо подгрузить связи, чтобы calculate_totals отработал корректно
        order = await OrderDAO.get_with_links(session, order_id)
        if order:
            order.calculate_totals()
            session.add(order)
            
        await session.commit()
    
    # ... остальные методы (get_all_orders, update_status) остаются без изменений ...
    @staticmethod
    async def get_all_orders(session: AsyncSession) -> List[Order]:
        return await OrderDAO.get_all(session)

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: Any) -> bool:
        """Update order status."""
        return await OrderDAO.update_status(session, order_id, new_status)