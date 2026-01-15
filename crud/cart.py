from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from models import Cart, CartItem

class CartDAO:
    @staticmethod
    async def get_cart(session: AsyncSession, user_id: int) -> Cart:
        """Get existing cart or create a new one."""
        cart = await session.get(Cart, user_id)
        if not cart:
            cart = Cart(user_id=user_id)
            session.add(cart)
            await session.commit()
            await session.refresh(cart)
        return cart

    @staticmethod
    async def add_item(session: AsyncSession, user_id: int, product_id: int) -> None:
        """Add item to cart or increment quantity."""
        # Ensure cart exists
        await CartDAO.get_cart(session, user_id)
        
        # Check if item already exists in cart
        stmt = select(CartItem).where(
            CartItem.cart_user_id == user_id,
            CartItem.product_id == product_id
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        
        if item:
            item.quantity += 1
            session.add(item)
        else:
            new_item = CartItem(cart_user_id=user_id, product_id=product_id, quantity=1)
            session.add(new_item)
        
        await session.commit()

    @staticmethod
    async def remove_item(session: AsyncSession, user_id: int, item_id: int) -> None:
        """Remove specific item from cart."""
        item = await session.get(CartItem, item_id)
        if item and item.cart_user_id == user_id:
            await session.delete(item)
            await session.commit()

    @staticmethod
    async def clear_cart(session: AsyncSession, user_id: int) -> None:
        """Delete the cart (and cascade delete items)."""
        cart = await session.get(Cart, user_id)
        if cart:
            await session.delete(cart)
            await session.commit()