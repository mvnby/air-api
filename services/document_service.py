from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload

from models import Order, OrderProductLink, OrderServiceLink
from services.google_service import google_service

# ID ваших шаблонов
TEMPLATES = {
    "contract": "1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg", # Договор поставки
    "offer": "1_p-XN5Myos5dP20LfYXodKbL8rvIRenZNBhiwqaYpNg",    # КП 
    "invoice": "13LlTvDxz5LXu4Wtt9pLkWf7JDG_rnt9vGoi49GMP9dY"   # Счет 
}

class DocumentService:
    @staticmethod
    async def create_document(session: AsyncSession, order_id: int, doc_type: str = "contract") -> str:
        """
        Создает документ указанного типа.
        """
        template_id = TEMPLATES.get(doc_type)
        if not template_id:
            return f"Ошибка: Неизвестный тип документа {doc_type}"

        # 1. Загрузка заказа с товарами
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.customer),
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service)
        )
        result = await session.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            return "Error: Order not found"
        
        # 2. Мягкие данные клиента
        customer_name = "Клиент"
        customer_inn = "-"
        customer_address = "-"
        customer_phone = "-"
        
        if order.customer:
             customer_name = order.customer.name or "Клиент"
             customer_inn = order.customer.inn or "-"
             customer_address = order.customer.legal_address or "-"
             customer_phone = order.customer.phone or "-"
        else:
             if order.delivery_address:
                 customer_phone = order.delivery_address

        # 3. Формирование таблицы (6 колонок под вашу шапку)
        # | № | Наименование товара | Ед. изм. | Кол-во | Цена | Сумма |
        table_rows = []
        counter = 1
        
        # Товары
        for link in order.product_links:
            title = link.product.title if link.product else "Товар"
            price = link.price
            qty = link.quantity
            total = price * qty
            
            row = [
                str(counter),           # 1. Номер
                title,                  # 2. Наименование
                "шт.",                  # 3. Ед. изм.
                str(qty),               # 4. Кол-во
                f"{price:.2f}",         # 5. Цена
                f"{total:.2f}"          # 6. Сумма
            ]
            table_rows.append(row)
            counter += 1

        # Услуги
        for link in order.service_links:
            title = link.service.title if link.service else "Услуга"
            price = link.price
            qty = link.quantity
            total = price * qty
            
            row = [
                str(counter),
                title,
                "шт.",
                str(qty),
                f"{price:.2f}",
                f"{total:.2f}"
            ]
            table_rows.append(row)
            counter += 1

        # 4. Замены
        replacements = {
            "{{order_id}}": str(order.id),
            "{{date}}": datetime.now().strftime("%d.%m.%Y"),
            "{{client_name}}": customer_name,
            "{{total_amount}}": f"{order.total_amount:.2f}",
            "{{phone}}": customer_phone,
            "{{inn}}": customer_inn,
            "{{address}}": customer_address
        }
        
        doc_names = {"contract": "Договор", "offer": "КП", "invoice": "Счет"}
        doc_title = f"{doc_names.get(doc_type, 'Док')} #{order.id} {customer_name}"
        
        link = google_service.generate_doc(template_id, doc_title, replacements, table_rows)
        return link