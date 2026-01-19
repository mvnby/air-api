from typing import Any
from sqladmin import ModelView
from sqlalchemy.orm import selectinload
from markupsafe import Markup
from wtforms import SelectField

# Импорты моделей и сессии
from models import Order, Service, OrderProductLink, OrderServiceLink, Customer, OrderInstaller, OrderStatus, Product
from core.database import async_session_maker
from sqlmodel import select

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

# --- ORDER INSTALLER INLINE ---
class OrderInstallerAdmin(ModelView, model=OrderInstaller):
    # Inline customization
    column_list = [OrderInstaller.installer, OrderInstaller.role, OrderInstaller.agreed_pay]
    form_columns = ["installer", "role", "agreed_pay", "is_paid_to_installer"]

# --- ORDER ADMIN ---
# --- ORDER ADMIN ---
STATUS_LABELS = {
    "new_lead": "Новый лид",
    "assessment": "Замер/Осмотр",
    "proposal": "КП отправлено",
    "negotiation": "Переговоры",
    "won_deposit": "Сделка (Предоплата)",
    "installation": "Монтаж",
    "completed": "Закрыто (Успех)",
    "canceled": "Отмена",
    "deferred": "Отложено"
}

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
        "user_id": "Telegram ID",
        "installation_date": "Дата установки",
        "assessment_date": "Дата замера"
    }
    
    column_sortable_list = [Order.id, Order.created_at, Order.status, Order.next_followup_date]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status", "next_followup_date"]
    
    # Inlines
    # Removed OrderInstallerAdmin to avoid conflict with custom manual handling
    inlines = []

    form_columns = [
        "customer",
        "delivery_address",
        "status",
        "installation_date",
        "assessment_date",
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
    
    # Restore choices for Status (since we changed column to String)
    form_overrides = dict(status=SelectField) 
    
    form_args = {
        "status": {
            "choices": [(s.value, STATUS_LABELS.get(s.value, s.value)) for s in OrderStatus], 
            "coerce": str
        }
    }

    # Custom formatters
    column_formatters = {
        "status": lambda m, a: STATUS_LABELS.get(m.status.value if hasattr(m.status, 'value') else m.status, m.status),
        "total_amount": lambda m, a: f"{m.total_amount:,.2f} руб.",
        "actions": lambda m, a: Markup(
            f"""
            <div class="btn-group">
                <a href="/admin/docs/generate/contract/{m.id}" class="btn btn-sm btn-outline-primary" target="_blank" title="Договор">📄</a>
                <a href="/admin/docs/generate/offer/{m.id}" class="btn btn-sm btn-outline-info" target="_blank" title="КП">💼</a>
                <a href="/admin/docs/generate/invoice/{m.id}" class="btn btn-sm btn-outline-success" target="_blank" title="Счет">💰</a>
                <a href="/admin/docs/generate/act/{m.id}" class="btn btn-sm btn-outline-secondary" target="_blank" title="Акт">✅</a>
                <a href="/admin/docs/generate/work_order/{m.id}" class="btn btn-sm btn-outline-warning" target="_blank" title="Наряд">🛠️</a>
                <div class="dropdown">
                    <button class="btn btn-sm btn-outline-dark dropdown-toggle" type="button" data-bs-toggle="dropdown">📦</button>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item" href="/admin/docs/generate/tn2/{m.id}" target="_blank">ТН-2</a></li>
                        <li><a class="dropdown-item" href="/admin/docs/generate/ttn1/{m.id}" target="_blank">ТТН-1</a></li>
                    </ul>
                </div>
            </div>
            """
        )
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
                
                # Update Installers if present in JSON
                if "installers" in items:
                    await OrderService.update_order_installers(session, model.id, items["installers"])

        # --- Phase 6: Inventory Safety Check ---
        # Prevent moving to PROPOSAL if stock < 3
        # Note: model.status is already updated to new value here
        
        if model.status == OrderStatus.PROPOSAL:
            product_ids = []
            
            # 1. If we just updated items, check them
            if items_json:
                items = json.loads(items_json)
                product_ids = [int(item['product_id']) for item in items]
            
            # 2. If no item update, check existing links
            elif not items_json:
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
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service),
            selectinload(self.model.installers).selectinload(OrderInstaller.installer)
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
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service),
            selectinload(self.model.installers).selectinload(OrderInstaller.installer)
        )

    # --- Notification Hook ---
    async def after_model_change(self, data: dict, model: Any, is_created: bool, request: Any) -> None:
        """
        Notify installers if new assignments are detected or status changes.
        """
        from services.bot_service import BotService
        
        # Check if status is actionable (Don't enable check for model.installers here as it might be stale)
        if model.status in [OrderStatus.INSTALLATION, OrderStatus.WON_DEPOSIT]:
            async with async_session_maker() as session:
                 # Re-fetch data to be sure
                 order = await session.get(Order, model.id)
                 if not order: return
                 # Use selectinload for installers
                 await session.refresh(order, attribute_names=["installers"])
                 
                 for link in order.installers:
                     # Fetch installer to get TG ID
                     await session.refresh(link, attribute_names=["installer"])
                     if link.installer and link.installer.telegram_id:
                         # Send notification (fire and forget)
                         # Real-world: Check if already notified to avoid spam
                         await BotService.notify_installer_new_order(
                             installer_tg_id=link.installer.telegram_id,
                             order_id=order.id,
                             address=order.delivery_address or "Адрес не указан",
                             date_str=order.installation_date.strftime("%d.%m.%Y") if order.installation_date else "Не назначена",
                             role=link.role
                         )