"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from core.database import get_session
from routers.api_admin import router as admin_router
from routers.api_content import router as content_router
from routers.api_products import router as products_router
from routers.api_proxy import router as proxy_router
from schemas import (
    OrderPayload,
    OrderResponse,
)
from models import Order, Customer, OrderStatus, OrderProductLink, CustomerType

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(admin_router)
router.include_router(content_router)
router.include_router(products_router)
router.include_router(proxy_router)
logger = logging.getLogger(__name__)

# --- ORDER ENDPOINTS ---

@router.post("/v1/orders", response_model=OrderResponse, operation_id="create_order")
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    
    Accepts customer information and cart items. Creates or updates customer record,
    creates order with NEW_LEAD status and lead_source=SITE.
    
    Returns created order details.
    """
    from services.order_service import OrderService
    from models import LeadSource
    
    # DEBUG: Log incoming payload
    logger.info(f"📦 Incoming order payload: customer={payload.customer.name}, items_count={len(payload.items)}")
    for idx, item in enumerate(payload.items):
        logger.info(f"   Item {idx}: product_id={item.product_id}, qty={item.quantity}, with_install={getattr(item, 'with_installation', 'N/A')}, install_price={getattr(item, 'installation_price', 'N/A')}")
    
    # If items provided, convert them
    items = [{
        "product_id": item.product_id, 
        "quantity": item.quantity,
        "with_installation": item.with_installation,
        "installation_price": item.installation_price,
        "installation_meta": item.installation_meta,
        "installation_options": item.installation_options
    } for item in payload.items]
    
    # Delegate to OrderService with SITE lead source
    order = await OrderService.create_from_website(
        session=session,
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        customer_email=payload.customer.email,
        customer_address=payload.customer.address,
        items=items,
        lead_source=LeadSource.SITE,
        comment=payload.comment,
        customer_type=payload.customer.type,
        customer_inn=payload.customer.inn,
        customer_legal_name=payload.customer.full_legal_name,
        customer_legal_address=payload.customer.legal_address,
        customer_iban=payload.customer.iban,
        customer_bic=payload.customer.bic,
        customer_bank_name=payload.customer.bank_name
    )
    
    # Отправляем уведомление админам в Telegram
    from core.config import settings
    from services.bot_service import BotService
    
    if settings.admin_list:
        # Подгружаем связи для уведомления
        # Подгружаем связи для уведомления
        await session.refresh(order, ["product_links", "service_links", "customer"])
        for link in order.product_links:
            await session.refresh(link, ["product"])
        
        # Формируем сообщение
        message_lines = [
            f"🌐 <b>ЗАКАЗ С САЙТА #{order.id}</b>",
            f"👤 {payload.customer.name}",
            f"📱 {payload.customer.phone}",
        ]
        
        if payload.customer.email:
            message_lines.append(f"📧 {payload.customer.email}")
        if payload.customer.address:
            message_lines.append(f"📍 {payload.customer.address}")
        if payload.comment:
            message_lines.append(f"💬 {payload.comment}")
            
        message_lines.append("")
        message_lines.append("🛒 <b>Товары:</b>")
        
        for link in order.product_links:

            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            product_line = f"▫️ {product_name} x{link.quantity} — {line_total} р."
            message_lines.append(product_line)
            
            # Добавляем строку монтажа если включен
            if link.is_installation_included:
                install_price = link.installation_price or 0
                install_line = f"   └ 🔧 Монтаж: {install_price} BYN"
                message_lines.append(install_line)
        
        # Добавляем услуги (включая Standalone монтаж)
        if order.service_links:
            for s_link in order.service_links:
                 title = s_link.title or "Услуга"
                 total = s_link.price * s_link.quantity
                 message_lines.append(f"🔧 {title} x{s_link.quantity} — {total} BYN")
        
        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        
        admin_text = "\n".join(message_lines)
        
        for admin_id in settings.admin_list:
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")
    
    return OrderResponse(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at
    )
