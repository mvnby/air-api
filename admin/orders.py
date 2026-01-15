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
        "docs",
        Order.created_at
    ]
    
    column_labels = {
        "id": "ID",
        "status": "Статус",
        "customer_id": "Клиент",
        "total_amount": "Сумма",
        "created_at": "Дата",
        "docs": "Документы",
        "delivery_address": "Адрес доставки",
        "user_id": "Telegram ID"
    }
    
    # Format customer display
    def format_customer(model, context):
        if model.customer:
            return model.customer.name
        return "—"
    
    # --- ФОРМАТТЕР ДЛЯ КНОПКИ ---
    def format_docs(model, context):
        # Ссылка ведет на наш новый роут
        url = f"/admin/docs/google/{model.id}"
        # Рисуем красивую кнопку с иконкой
        return Markup(f'<a href="{url}" target="_blank" class="btn btn-sm btn-outline-success" title="Создать договор в Google Docs"><i class="fa-brands fa-google-drive"></i> G-Doc</a>')
    
    column_formatters = {
        Order.customer_id: format_customer,
        "docs": format_docs
    }
    
    column_sortable_list = [Order.id, Order.created_at, Order.status]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status"]
    
    # Form columns
    form_columns = [
        "customer",
        "delivery_address",
        "status",
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