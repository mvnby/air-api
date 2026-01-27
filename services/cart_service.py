from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from crud.cart import CartDAO
from services.order_service import OrderService
from services.product_service import ProductService

class CartService:
    @staticmethod
    async def get_cart_summary(session: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Returns cart details suitable for display."""
        cart = await CartDAO.get_cart(session, user_id)
        
        items_summary = []
        total_price = 0
        
        for item in cart.items:
            # item.product подгружается автоматически благодаря lazy="joined" в модели
            line_sum = item.product.price * item.quantity
            total_price += line_sum
            items_summary.append({
                "id": item.id,
                "product_id": item.product_id,
                "title": item.product.title,
                "price": item.product.price,
                "quantity": item.quantity,
                "line_sum": line_sum
            })
            
        return {
            "items": items_summary,
            "total_price": total_price,
            "is_empty": len(items_summary) == 0
        }

    @staticmethod
    async def add_product(session: AsyncSession, user_id: int, product_id: int):
        await CartDAO.add_item(session, user_id, product_id)

    @staticmethod
    async def clear_cart(session: AsyncSession, user_id: int):
        await CartDAO.clear_cart(session, user_id)

    @staticmethod
    async def checkout(session: AsyncSession, user_id: int, contact_info: str, username: str = None, full_name: str = None):
        """
        Convert Cart to Order.
        """
        cart_summary = await CartService.get_cart_summary(session, user_id)
        
        if cart_summary["is_empty"]:
            raise ValueError("Cart is empty")

        items_data = {
            "products": [
                {
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "price": item["price"]
                } for item in cart_summary["items"]
            ],
            "services": []
        }
        
        # Создаем заказ
        order = await OrderService.create_order(
            session=session,
            user_id=user_id,
            contact_info=contact_info,
            items_data=items_data,
            username=username,
            full_name=full_name
        )
        
        # ВАЖНОЕ ИСПРАВЛЕНИЕ:
        # Принудительно обновляем заказ и подгружаем связи, чтобы total_amount посчитался верно
        # И чтобы product_links.product были доступны для уведомлений
        await session.refresh(order, ["product_links", "service_links"])
        
        # Подгружаем product для каждого product_link (для telegram уведомлений)
        for link in order.product_links:
            await session.refresh(link, ["product"])
        
        # Очищаем корзину
        await CartService.clear_cart(session, user_id)
        
        return order