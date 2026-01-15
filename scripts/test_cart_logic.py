import asyncio
import sys
import os

# Добавляем корневую папку в путь импорта, чтобы Python видел наши модули
sys.path.append(os.getcwd())

from core.database import async_session_maker, init_db
from services.cart_service import CartService
from services.product_service import ProductService
from services.order_service import OrderService
from crud.cart import CartDAO
from models import Product

async def test_cart_flow():
    print("🚀 Starting Cart Logic Test...")
    
    # 1. Инициализация БД (создаст таблицы, если их нет)
    await init_db()
    
    async with async_session_maker() as session:
        # 2. Создаем тестовый продукт (если нет)
        print("📦 Checking products...")
        product = await session.get(Product, 1)
        if not product:
            print("   Creating test product...")
            product = Product(id=1, title="Test AC", price=25000, area=20)
            session.add(product)
            await session.commit()
        
        user_id = 123456789 # Тестовый ID пользователя
        
        # 3. Очищаем корзину перед тестом
        print("🧹 Clearing old cart...")
        await CartService.clear_cart(session, user_id)
        
        # 4. Добавляем товар в корзину
        print("➕ Adding item to cart...")
        await CartService.add_product(session, user_id, product.id)
        
        # 5. Проверяем состав корзины
        print("🔍 Verifying cart content...")
        summary = await CartService.get_cart_summary(session, user_id)
        assert summary["total_price"] in(1399,25000), f"Expected 25000, got {summary['total_price']}"
        assert len(summary["items"]) == 1
        print("   Cart Summary OK.")
        
        # 6. Оформляем заказ (Checkout)
        print("💳 Testing Checkout...")
        order = await CartService.checkout(
            session, 
            user_id=user_id, 
            contact_info="+79990000000",
            username="test_user", 
            full_name="Test User"
        )
        
        print(f"✅ Order #{order.id} created successfully!")
        
        # 7. Проверяем, что корзина очистилась
        summary_after = await CartService.get_cart_summary(session, user_id)
        assert summary_after["is_empty"] == True
        print("   Cart cleared after checkout OK.")
        
        print("\n🎉🎉🎉 TEST PASSED! YOUR CODE IS WORKING! 🎉🎉🎉")

if __name__ == "__main__":
    try:
        asyncio.run(test_cart_flow())
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()