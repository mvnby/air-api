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
        "actions": "Документы",
        "delivery_address": "Адрес доставки",
        "user_id": "Telegram ID"
    }
    
    # Format customer display
    def format_customer(model, context):
        if model.customer:
            return model.customer.name
        return "—"

    def format_status(model, context):
        status = model.status.value if hasattr(model.status, "value") else str(model.status)
        colors = {
            "new_lead": "info",
            "assessment": "warning",
            "proposal": "primary", # purple in custom css but primary here
            "negotiation": "warning",
            "won_deposit": "success",
            "installation": "success",
            "completed": "primary",
            "canceled": "danger",
            "deferred": "secondary"
        }
        color = colors.get(status.lower(), "secondary")
        return Markup(f'<span class="badge bg-{color}">{status.upper()}</span>')
    
     # --- ОБНОВЛЕННЫЙ ФОРМАТТЕР ДЛЯ КНОПОК ---
    def format_actions(model, context):
        # Три разные кнопки
        btn_offer = f'<a href="/admin/docs/generate/offer/{model.id}" target="_blank" class="btn btn-sm btn-outline-info" title="Коммерческое предложение"><i class="fa-solid fa-file-invoice"></i> КП</a>'
        btn_invoice = f'<a href="/admin/docs/generate/invoice/{model.id}" target="_blank" class="btn btn-sm btn-outline-warning ms-1" title="Счет на оплату"><i class="fa-solid fa-money-bill"></i> Счет</a>'
        btn_contract = f'<a href="/admin/docs/generate/contract/{model.id}" target="_blank" class="btn btn-sm btn-outline-success ms-1" title="Договор"><i class="fa-solid fa-file-contract"></i> Договор</a>'
        
        return Markup(f'<div class="d-flex">{btn_offer}{btn_invoice}{btn_contract}</div>')
    
    column_formatters = {
        Order.customer_id: format_customer,
        Order.status: format_status,
        "actions": format_actions
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