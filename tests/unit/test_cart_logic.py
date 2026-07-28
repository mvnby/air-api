import pytest
from services.cart_service import CartService
from models import Order, Product


async def test_cart_flow(db, tenant_scope):
    # 1. Create test product
    product = Product(id=1, title="Test AC", slug="test-ac", price=25000, specs={"area_m2": 20})
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    user_id = 123456789 
    
    # 2. Clear cart
    await CartService.clear_cart(db, user_id)
    
    # 3. Add to cart
    await CartService.add_product(db, user_id, product.id)
    
    # 4. Verify content
    summary = await CartService.get_cart_summary(db, user_id)
    # The original script allowed 1399 or 25000 (maybe legacy logic?), let's assume 25000 based on price
    assert summary["total_price"] == 25000
    assert len(summary["items"]) == 1
    
    # 5. Checkout
    checkout_result = await CartService.checkout(
        db, 
        user_id=user_id,
        contact_info="+79990000000",
        tenant_scope=tenant_scope,
        username="test_user",
        full_name="Test User"
    )

    assert checkout_result["order_id"] is not None
    assert checkout_result["contact_info"] == "+79990000000"
    assert checkout_result["items_count"] == 1
    assert checkout_result["total_amount"] == 25000
    order = await db.get(Order, checkout_result["order_id"])
    assert order is not None
    assert order.tenant_id == tenant_scope.tenant_id
    assert order.storefront_id == tenant_scope.storefront_id

    # 6. Verify cart cleared
    summary_after = await CartService.get_cart_summary(db, user_id)
    assert summary_after["is_empty"] is True


async def test_checkout_empty_cart_raises(db, tenant_scope):
    user_id = 777
    await CartService.clear_cart(db, user_id)

    with pytest.raises(ValueError, match="Cart is empty"):
        await CartService.checkout(
            db,
            user_id=user_id,
            contact_info="+79990000000",
            tenant_scope=tenant_scope,
            username="empty_user",
            full_name="Empty User",
        )
