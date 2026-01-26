#!/usr/bin/env python3
"""
Test snapshot pricing implementation for installation services.
Verifies that orders with installation are correctly stored in database.
"""
import asyncio
import sys
import os

sys.path.append(os.getcwd())

from core.database import async_session_maker, init_db
from services.order_service import OrderService
from models import Order, OrderProductLink, Product, LeadSource
from sqlmodel import select

async def test_snapshot_pricing():
    print("🚀 Testing Snapshot Pricing Implementation...")
    
    await init_db()
    
    async with async_session_maker() as session:
        # 1. Get or create test product
        print("\n📦 Fetching test product...")
        product = await session.get(Product, 1)
        if not product:
            print("   ❌ No product with ID=1 found. Please create a product first.")
            return False
        
        print(f"   ✓ Found product: {product.title} (Price: {product.price} р.)")
        
        # 2. Create order WITH installation
        print("\n📝 Creating order WITH installation...")
        order_data = {
            "customer_name": "Тестовый Клиент",
            "customer_phone": "+375991234567",
            "customer_email": "test@example.com",
            "customer_address": "г. Минск, ул. Тестовая 1",
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_price": 260,
                    "installation_meta": {
                        "base_rate": 360,
                        "discount": 100,
                        "source": "web_calculator"
                    }
                }
            ],
            "lead_source": LeadSource.SITE,
            "comment": "Тестовый заказ для snapshot pricing"
        }
        
        order = await OrderService.create_from_website(
            session=session,
            **order_data
        )
        
        print(f"   ✓ Created order #{order.id}")
        
        # 3. Verify order product link
        print("\n🔍 Verifying order product link...")
        stmt = select(OrderProductLink).where(OrderProductLink.order_id == order.id)
        result = await session.execute(stmt)
        link = result.scalar_one()
        
        print(f"   Product ID: {link.product_id}")
        print(f"   Quantity: {link.quantity}")
        print(f"   Product Price: {link.price} р.")
        print(f"   Installation Included: {link.is_installation_included}")
        print(f"   Installation Price: {link.installation_price} р.")
        print(f"   Installation Details: {link.installation_details}")
        
        # 4. Verify total calculation
        print("\n💰 Verifying total calculation...")
        expected_total = (link.price + link.installation_price) * link.quantity
        print(f"   Expected Total: {expected_total} р.")
        print(f"   Actual Total: {order.total_amount} р.")
        
        # 5. Assertions
        assert link.is_installation_included == True, "Installation should be included"
        assert link.installation_price == 260, f"Installation price should be 260, got {link.installation_price}"
        assert link.installation_details is not None, "Installation details should be set"
        assert link.installation_details.get("source") == "web_calculator", "Source should be web_calculator"
        assert order.total_amount == expected_total, f"Total mismatch: expected {expected_total}, got {order.total_amount}"
        
        print("\n✅ All assertions passed!")
        
        # 6. Create order WITHOUT installation for comparison
        print("\n📝 Creating order WITHOUT installation...")
        order_no_install = await OrderService.create_from_website(
            session=session,
            customer_name="Клиент без монтажа",
            customer_phone="+375992345678",
            customer_email=None,
            customer_address="г. Витебск",
            items=[
                {
                    "product_id": product.id,
                    "quantity": 2,
                    "with_installation": False,
                    "installation_price": 0,
                    "installation_meta": None
                }
            ],
            lead_source=LeadSource.SITE,
            comment=None
        )
        
        print(f"   ✓ Created order #{order_no_install.id}")
        
        # Verify no installation
        stmt2 = select(OrderProductLink).where(OrderProductLink.order_id == order_no_install.id)
        result2 = await session.execute(stmt2)
        link2 = result2.scalar_one()
        
        assert link2.is_installation_included == False, "Installation should NOT be included"
        assert link2.installation_price == 0, "Installation price should be 0"
        assert order_no_install.total_amount == product.price * 2, "Total should be product price x2"
        
        print("   ✓ Verified: No installation fields set correctly")
        
        print("\n🎉 TEST PASSED! Snapshot pricing is working correctly!")
        return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_snapshot_pricing())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
