from typing import Any
from sqladmin import ModelView
from sqlalchemy.orm import selectinload
from markupsafe import Markup

# Импорты моделей и сессии
from models import Order, Service, OrderProductLink, OrderServiceLink, Customer
from core.database import async_session_maker

class ServiceAdmin(ModelView, model=Service):
    name = "Услуга"
    name_plural = "Услуги"
    icon = "fa-solid fa-hand-holding-heart"
    column_list = [Service.id, Service.title, Service.base_price]
    column_labels = {
        "id": "ID",
        "title": "Название",
        "base_price": "Базовая цена (руб.)"
    }

class OrderProductLinkAdmin(ModelView, model=OrderProductLink):
    def is_visible(self, request): return False

class OrderServiceLinkAdmin(ModelView, model=OrderServiceLink):
    def is_visible(self, request): return False

class OrderAdmin(ModelView, model=Order):
    name = "Заказ"
    name_plural = "Заказы"
    icon = "fa-solid fa-cart-shopping"
    
    edit_template = "sqladmin/order_edit.html"
    
    column_list = [
        Order.id, 
        Order.status, 
        Order.customer_id,
        "total_amount", 
        "actions",
        Order.created_at
    ]
    
    column_labels = {
        "id": "ID",
        "status": "Статус",
        "customer_id": "Клиент",
        "total_amount": "Сумма",
        "created_at": "Дата",
        "next_followup_date": "След. касание",
        "actions": "Документы",
        "delivery_address": "Адрес доставки",
        "user_id": "Telegram ID"
    }
    
    # ... previous code ...

    column_sortable_list = [Order.id, Order.created_at, Order.status, Order.next_followup_date]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status", "next_followup_date"]
    
    # Form columns
    form_columns = [
        "customer",
        "delivery_address",
        "status",
        "next_followup_date",
        "user_id"
    ]
    
    # AJAX Select2 for customer lookup
    form_ajax_refs = {
        "customer": {
            "fields": ["name", "phone", "inn"],
            "order_by": "name",
            "placeholder": "Поиск по имени, телефону или ИНН...",
            "minimum_input_length": 0,
        }
    }

    # --- ИСПРАВЛЕННЫЙ МЕТОД ---
    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Any) -> None:
        """Handle dynamic items from the custom form."""
        import json
        from services.order_service import OrderService
        
        form_data = await request.form()
        items_json = form_data.get("items_json")
        
        if items_json:
            items = json.loads(items_json)
            # ВАЖНО: Создаем сессию и передаем её первым аргументом
            async with async_session_maker() as session:
                await OrderService.update_order_links(session, model.id, items)

        # --- Phase 6: Inventory Safety Check ---
        # Prevent moving to PROPOSAL if stock < 3
        # Note: model.status is already updated to new value here
        from models import OrderStatus, Product
        from sqlmodel import select
        
        if model.status == OrderStatus.PROPOSAL:
            product_ids = []
            
            # 1. If we just updated items, check them
            if items_json:
                items = json.loads(items_json)
                product_ids = [int(item['product_id']) for item in items]
            
            # 2. If no item update, check existing links
            # We must handle the async loading carefully. 
            # If not loaded, we can't access model.product_links easily without await.
            # But form_edit_query uses selectinload, so it should be there.
            elif not items_json:
                # Fallback to current links if available
                # Note: modifying product_links directly in form might not reflect here if standard relationship handling is bypassed
                # But for our custom JS form, items_json is the source of truth.
                # If items_json is MISSING, it means we are just changing status via list or detail view.
                product_ids = [link.product_id for link in model.product_links]
            
            if product_ids:
                async with async_session_maker() as session:
                    stmt = select(Product).where(Product.id.in_(product_ids))
                    res = await session.execute(stmt)
                    products = res.scalars().all()
                    
                    low_stock_items = []
                    for p in products:
                        # Assuming stock_quantity is mandatory field, default 0
                        if p.stock_quantity < 3:
                            low_stock_items.append(f"{p.title} ({p.stock_quantity})")
                    
                    if low_stock_items:
                        items_str = ", ".join(low_stock_items)
                        raise ValueError(f"⛔ STOP: Low Stock Alert! The following items have < 3 units: {items_str}. Cannot send Proposal.")

    def form_edit_query(self, request):
        query = super().form_edit_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )