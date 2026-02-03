import pytest
from sqlmodel import select
from services.order_service import OrderService
from models import Product, OrderProductLink, LeadSource

async def test_snapshot_pricing(db):
    # 1. Create test product
    product = Product(id=63, title="Hero Product", slug="hero-product", price=2500, area=30)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    # 2. Create order WITH installation
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
        session=db,
        **order_data
    )
    
    # 3. Verify order product link
    stmt = select(OrderProductLink).where(OrderProductLink.order_id == order.id)
    result = await db.execute(stmt)
    link = result.scalar_one()
    
    # 4. Verify total calculation
    expected_total = (link.price + link.installation_price) * link.quantity
    
    assert link.is_installation_included is True
    assert link.installation_price == 260
    assert link.installation_details is not None
    assert link.installation_details.get("source") == "web_calculator"
    assert order.total_amount == expected_total

async def test_order_without_installation(db):
    # 1. Create test product
    product = Product(id=63, title="Hero Product", slug="hero-product", price=2500, area=30)
    db.add(product)
    await db.commit()
    await db.refresh(product)

    # 2. Create order WITHOUT installation
    order_no_install = await OrderService.create_from_website(
        session=db,
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
    
    # Verify no installation
    stmt = select(OrderProductLink).where(OrderProductLink.order_id == order_no_install.id)
    result = await db.execute(stmt)
    link = result.scalar_one()
    
    assert link.is_installation_included is False
    assert link.installation_price == 0
    assert order_no_install.total_amount == product.price * 2
