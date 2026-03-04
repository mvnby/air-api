from typing import Dict, Any, TypedDict
from sqlalchemy.ext.asyncio import AsyncSession
from crud.cart import CartDAO
from services.order_service import OrderService


class CheckoutResultDTO(TypedDict):
    order_id: int
    total_amount: float
    contact_info: str
    items_count: int

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
    async def checkout(
        session: AsyncSession,
        user_id: int,
        contact_info: str,
        username: str = None,
        full_name: str = None,
    ) -> CheckoutResultDTO:
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

        # Очищаем корзину
        await CartService.clear_cart(session, user_id)

        if order.id is None:
            raise RuntimeError("Order ID was not assigned after checkout")

        return {
            "order_id": int(order.id),
            "total_amount": float(order.total_amount or 0),
            "contact_info": contact_info,
            "items_count": len(cart_summary["items"]),
        }
