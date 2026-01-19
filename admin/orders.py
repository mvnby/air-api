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
        Order.created_at
    ]
    
    column_labels = {
        "id": "ID",
        "status": "Статус",
        "customer_id": "Клиент",
        "total_amount": "Сумма",
        "created_at": "Дата",
        "next_followup_date": "След. касание",
        "delivery_address": "Адрес доставки",
        "user_id": "Telegram ID",
        "installation_date": "Дата установки",
        "assessment_date": "Дата замера",
        "contract_date": "Дата договора"
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
        "contract_date",
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
        "total_amount": lambda m, a: f"{m.total_amount:,.2f} руб."
    }

    # --- ИСПРАВЛЕННЫЙ МЕТОД ---
    async def update_model(self, request, pk: Any, data: dict) -> Any:
        import json
        from models import Product, OrderProductLink, OrderServiceLink, OrderInstaller
        import logging
        
        # Ensure pk is an integer for DB operations
        try:
            order_id = int(pk)
        except (ValueError, TypeError):
            # Fallback if pk is somehow not convertable, though unlikely for existing ID
            order_id = pk

        logger = logging.getLogger(__name__)
        
        # Check if items_json is in data or need to be fetched from request form
        items_json = data.pop("items_json", None)
        
        if items_json is None:
            # Fallback: try to get from request form directly if not in processed data
            form_data = await request.form()
            items_json = form_data.get("items_json")
            logger.info(f"update_model: items_json extracted from request form: {bool(items_json)}")
        else:
            logger.info(f"update_model: items_json found in data: {bool(items_json)}")

        # 1. Update basic fields
        model = await super().update_model(request, pk, data)
        
        # 2. If items_json is present, parse it and update relationships
        if items_json:
            try:
                items_data = json.loads(items_json)
                session = self.session_maker()
                
                async with session.begin():
                    # Clear existing links (using integer order_id)
                    await session.execute(
                        OrderProductLink.__table__.delete().where(OrderProductLink.order_id == order_id)
                    )
                    await session.execute(
                        OrderServiceLink.__table__.delete().where(OrderServiceLink.order_id == order_id)
                    )
                    await session.execute(
                        OrderInstaller.__table__.delete().where(OrderInstaller.order_id == order_id)
                    )
                    
                    # Add new products
                    for prod in items_data.get("products", []):
                        new_link = OrderProductLink(
                            order_id=order_id,
                            product_id=int(prod["product_id"]),
                            quantity=int(prod["quantity"]),
                            price=int(prod["price"])
                        )
                        session.add(new_link)
                        
                    # Add new services
                    for serv in items_data.get("services", []):
                        new_link = OrderServiceLink(
                            order_id=order_id,
                            service_id=int(serv["service_id"]),
                            quantity=int(serv["quantity"]),
                            price=int(serv["price"])
                        )
                        session.add(new_link)
                        
                    # Add new installers
                    for inst in items_data.get("installers", []):
                        new_inst = OrderInstaller(
                            order_id=order_id,
                            installer_id=int(inst["installer_id"]),
                            agreed_pay=int(inst["agreed_pay"]),
                            role=inst["role"]
                        )
                        session.add(new_inst)
                        
                await session.commit()
                
                # Recalculate order totals after updating items
                # Need to reload the order with all relationships
                from sqlmodel import select
                from sqlalchemy.orm import selectinload
                
                query = select(Order).where(Order.id == order_id).options(
                    selectinload(Order.product_links),
                    selectinload(Order.service_links),
                    selectinload(Order.installers)
                )
                result = await session.execute(query)
                refreshed_order = result.scalar_one()
                
                refreshed_order.calculate_totals()
                session.add(refreshed_order)
                await session.commit()
                
            except Exception as e:
                # Log error but don't fail the whole request if possible, 
                # or raise to let user know
                import logging
                logging.getLogger(__name__).error(f"Error updating order items: {e}")
                raise e
        
        # --- Phase 6: Inventory Safety Check ---
        # Prevent moving to PROPOSAL if stock < 3
        # Note: model.status is already updated to new value here
        
        if model.status == OrderStatus.PROPOSAL:
            product_ids = []
            
            # 1. If we just updated items, check them
            if items_json:
                items = json.loads(items_json)
                product_ids = [int(item['product_id']) for item in items.get('products', [])]
            
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

        return model

    def form_edit_query(self, request):
        query = super().form_edit_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service),
            selectinload(self.model.installers).selectinload(OrderInstaller.installer),
            selectinload(self.model.documents)
        )

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service),
            selectinload(self.model.documents)
        )

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(
            selectinload(self.model.customer),
            selectinload(self.model.product_links).selectinload(OrderProductLink.product),
            selectinload(self.model.service_links).selectinload(OrderServiceLink.service),
            selectinload(self.model.installers).selectinload(OrderInstaller.installer),
            selectinload(self.model.documents)
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

    async def edit(self, request):
        """Override to handle 'Save and continue' redirect."""
        from starlette.responses import RedirectResponse
        
        # Check form data for button value
        form = await request.form()
        save_action = form.get("save")

        # Call parent edit method
        response = await super().edit(request)

        # If it's a redirect (success) and user clicked 'Save and continue'
        if isinstance(response, RedirectResponse) and save_action == "Save and continue editing":
            # Extract order ID from current URL
            # Path format: /admin/order/edit/{id}
            path_parts = request.url.path.split('/')
            if 'edit' in path_parts:
                order_id = path_parts[-1]
                # Redirect back to the same edit page
                return RedirectResponse(
                    url=f"/admin/order/edit/{order_id}",
                    status_code=302
                )
        
        return response