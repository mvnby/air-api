from sqladmin import ModelView
from sqlalchemy.orm import selectinload
from models import Order

class OrderAdmin(ModelView, model=Order):
    name = "Заказ"
    name_plural = "Заказы"
    icon = "fa-solid fa-cart-shopping"
    column_list = [Order.id, Order.status, Order.product, Order.user_id, Order.phone, Order.created_at]
    column_labels = {
        "id": "ID",
        "status": "Статус",
        "product": "Заказ",
        "user_id": "Telegram ID",
        "phone": "Телефон",
        "created_at": "Дата"
    }
    column_sortable_list = [Order.id, Order.created_at, Order.status]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status"]
    
    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.product))

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(selectinload(self.model.product))
