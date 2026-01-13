from sqladmin import ModelView
from sqlalchemy.orm import selectinload
from models import Order, Service, OrderProductLink, OrderServiceLink

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
        Order.customer_name, 
        Order.customer_phone, 
        "total_amount", 
        Order.created_at
    ]
    
    column_labels = {
        "id": "ID",
        "status": "Статус",
        "customer_name": "Клиент",
        "customer_phone": "Телефон",
        "total_amount": "Сумма",
        "created_at": "Дата",
        "customer_email": "Email",
        "address": "Адрес",
        "user_id": "Telegram ID"
    }
    
    column_sortable_list = [Order.id, Order.created_at, Order.status]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status"]
    
    # Явно указываем поля для формы
    form_columns = [
        "customer_name",
        "customer_phone",
        "customer_email",
        "address",
        "status",
        "user_id"
    ]

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Any) -> None:
        """Handle dynamic items from the custom form."""
        import json
        from models import OrderProductLink, OrderServiceLink
        from core.database import async_session_maker
        from sqlalchemy import delete
        
        form_data = await request.form()
        items_json = form_data.get("items_json")
        
        if items_json:
            items = json.loads(items_json)
            
            # We need to manage links manually or via session
            # Since SQLAdmin might have its own session management, 
            # we'll use a local session for the links update to be safe, 
            # but ideally we should use the one in request or similar.
            # SQLAdmin 0.22.0 usually provides the session in some way.
            
            async with async_session_maker() as session:
                # 1. Clear existing links for this order
                if not is_created:
                    await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == model.id))
                    await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == model.id))
                
                # 2. Add new links
                for p in items.get("products", []):
                    link = OrderProductLink(
                        order_id=model.id,
                        product_id=p["product_id"],
                        quantity=p["quantity"],
                        price=p["price"]
                    )
                    session.add(link)
                
                for s in items.get("services", []):
                    link = OrderServiceLink(
                        order_id=model.id,
                        service_id=s["service_id"],
                        quantity=s["quantity"],
                        price=s["price"]
                    )
                    session.add(link)
                
                await session.commit()

    def form_edit_query(self, request):
        query = super().form_edit_query(request)
        return query.options(
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service)
        )
