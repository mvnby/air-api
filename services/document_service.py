from sqlalchemy.ext.asyncio import AsyncSession
from models import Order
from services.google_service import google_service
from datetime import datetime

class DocumentService:
    @staticmethod
    async def create_google_contract(session: AsyncSession, order_id: int) -> str:
        """
        Создает Google Doc для заказа и возвращает ссылку.
        """
        # 1. Получаем данные
        order = await session.get(Order, order_id)
        if not order:
            return "Error: Order not found"

        # Подгружаем связи
        await session.refresh(order, ["customer", "product_links"])
        
        # 2. Готовим данные для замены
        # БЕЗОПАСНОЕ ПОЛУЧЕНИЕ ИМЕНИ
        customer_name = "Частное лицо"
        customer_inn = ""
        # Проверяем, есть ли поле delivery_address в модели, если нет - ставим пустую строку
        customer_address = getattr(order, "delivery_address", "") or ""
        
        # Если есть привязанный клиент (B2B)
        if order.customer:
             customer_name = order.customer.name
             customer_inn = order.customer.inn or ""
        
        # Если клиента нет, пробуем найти хоть какие-то данные
        # (Например, можно сохранять username в delivery_address временно, как мы делали в боте)
        if customer_name == "Частное лицо" and customer_address:
             # Если в адресе записан телефон или имя
             pass

        replacements = {
            "{{order_id}}": str(order.id),
            "{{date}}": datetime.now().strftime("%d.%m.%Y"),
            "{{client_name}}": customer_name,
            "{{total_amount}}": str(order.total_amount),
            "{{phone}}": customer_address,
            "{{inn}}": customer_inn
        }
        
        doc_title = f"Договор #{order.id} - {customer_name}"
        
        # 3. Вызываем Google API
        # Тут может вылететь ошибка Quota, поэтому обернем в try внутри сервиса, 
        # но google_service уже возвращает текст ошибки, так что просто вернем его.
        link = google_service.create_contract_from_template(doc_title, replacements)
        return link